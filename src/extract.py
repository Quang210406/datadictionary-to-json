import re
from pathlib import Path

import pandas as pd

import kinds

# Read one sheet as a raw grid: drop fully empty rows
def read_excel_df(path: str, sheet_name=0) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name, header=None)
    return df.dropna(how="all")

# Turn the raw grid into plain CSV text for the AI agent to read.
def df_to_text(df: pd.DataFrame) -> str:
    return df.to_csv(index=False, header=False)


# The anchor words themselves now live with the rest of each source kind's
# definition, in kinds.py — they used to sit here in a HEADER_ANCHORS dict of
# their own, which is how one of them came to be missing without anything
# failing. Finding the header row is still this module's job; knowing which
# words to look for is a property of the document kind.

# A column-header row spans the table; a stray metadata line does not.
# This is what stops "Source and Target File Name" (one populated cell) in a
# hop spec's metadata block from being mistaken for the header row.
MIN_HEADER_CELLS = 4


def _is_header_row(cells, anchors) -> bool:
    if len(cells) < MIN_HEADER_CELLS:
        return False
    claimed = set()
    for words in anchors:
        hits = {i for i, cell in enumerate(cells) if any(w in cell for w in words)}
        hits -= claimed
        if not hits:
            return False
        claimed.add(min(hits))
    return True


# How many data rows the agent should have produced records for.
#
# The single-file version subtracted a hard-coded 3 header rows. Layouts now
# differ per source (a hop spec carries a metadata block a dozen rows deep),
# so instead we locate the column-header row and count what follows it.
# Returns None when no header row is recognisable — the caller reports the
# record count as a metric but does not fail the run on a number it guessed.
def expected_row_count(df: pd.DataFrame, source_kind: str, anchors=None):
    """`anchors` overrides the registry's defaults, for an archive whose sheets
    use different captions. None means "use what kinds.py declares"."""
    anchors = anchors or kinds.header_anchors(source_kind)
    if anchors is None:
        return None
    for position in range(len(df)):
        cells = [
            str(value).strip().lower()
            for value in df.iloc[position]
            if pd.notna(value)
        ]
        if _is_header_row(cells, anchors):
            return len(df) - position - 1
    return None


# ------------------------------------------------------------------ SQL

# Comments, both dialects. Stripped before anything else looks at a .sql file:
# every real script in the archive opens with a "-- DDL for View X" banner, so
# the statement is never the first thing in the file, and a pattern that
# ignored comments would either have to hunt for the statement anywhere in the
# text or find nothing at all. Hunting is the dangerous half — a CREATE VIEW
# written inside a comment would then classify the file.
SQL_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)


def strip_sql_comments(text: str) -> str:
    """The script with its comments blanked out.

    Replaced with a space rather than deleted, so `CREATE/*x*/VIEW` cannot be
    welded into one token and two words never become one.
    """
    return SQL_COMMENT.sub(" ", text or "")


# Oracle writes a pile of modifiers between CREATE and the object keyword
# ("CREATE OR REPLACE FORCE EDITIONABLE VIEW"), and splits the line wherever
# it likes — one real file has CREATE alone on line 4 and the rest on line 5.
# So: bare words and whitespace only, non-greedy, and bounded. Bounded matters
# — an unbounded run would let a CREATE at the top of the file reach a TABLE
# far below it and classify on a pairing that is not a statement at all.
# Overshooting the bound fails CLOSED: the file is unrecognised, checkpoint 1
# rejects it and nothing is spent on it.
MAX_STATEMENT_MODIFIERS = 6


def _statement_pattern():
    """Built from the registry, so a new kind needs no edit here.

    Rebuilt per call rather than compiled at import. It costs microseconds
    against a run that reads whole files, and it means the pattern can never
    be stale with respect to the registry it is supposed to reflect — which
    is the entire property this indirection exists to provide.
    """
    tokens = "|".join(re.escape(word) for word in sorted(kinds.statements()))
    return re.compile(
        r"\A\s*CREATE(?:\s+\w+){0,%d}?\s+(%s)\b" % (MAX_STATEMENT_MODIFIERS, tokens),
        re.I)


def classify_sql(text: str):
    r"""Which source kind this .sql file is, by the statement it opens with.

    Returns None when nothing matches, and None means exactly that — the
    caller must report it, never fall back to a default kind. A default is
    what made a CREATE TABLE arrive labelled "view": it passed every check,
    because every check was then asking whether a view was read correctly.

    Anchored at \A, after comments are stripped. `search` would be wrong in
    both directions: it would accept a CREATE VIEW buried in a banner comment
    (a file classified by its documentation, not its code), and it would
    accept the first CREATE anywhere in a script whose real first statement
    was something else.
    """
    match = _statement_pattern().search(strip_sql_comments(text))
    if not match:
        return None
    return kinds.statements()[match.group(1).upper()]


# The declared column list of a CREATE statement. Object names contain spaces,
# so the name is matched as a quoted string OR a bare token before the "(".
# The object keyword comes from the registry for the same reason classify_sql's
# does: a CTAS may declare a column list too, and it is the same anchor.
def _header_pattern():
    tokens = "|".join(re.escape(word) for word in sorted(kinds.statements()))
    return re.compile(r'(?:%s)\s+("(?:[^"]+)"|\S+)\s*\((.*?)\)\s*AS\s' % tokens,
                      re.S | re.I)


def read_sql_text(path: str) -> str:
    """A .sql file is already text; no grid, no sheet, nothing to flatten."""
    return Path(path).read_text(errors="ignore")


def declared_object(text: str):
    """(object name, [declared columns]) from the CREATE header.

    The header is the completeness anchor for SQL: a spreadsheet says how many
    rows it has, a CREATE says how many columns it declares. Returns (None, [])
    when no header is recognisable, and the caller then reports the record
    count without judging it.

    Reads the comment-stripped text, so a column list quoted in a banner
    cannot be mistaken for the real one.
    """
    match = _header_pattern().search(strip_sql_comments(text))
    if not match:
        return None, []
    return match.group(1).strip('"'), re.findall(r'"([^"]+)"', match.group(2))


def expected_column_count(text: str):
    columns = declared_object(text)[1]
    return len(columns) or None
