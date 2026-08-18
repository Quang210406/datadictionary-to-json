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
def expected_row_count(df: pd.DataFrame, source_kind: str):
    anchors = kinds.header_anchors(source_kind)
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


# ---------------------------------------------------------------- SQL views

# The declared column list of a CREATE VIEW. View names contain spaces, so the
# name is matched as a quoted string OR a bare token before the "(".
VIEW_HEADER = re.compile(r'VIEW\s+("(?:[^"]+)"|\S+)\s*\((.*?)\)\s*AS\s', re.S | re.I)


def read_sql_text(path: str) -> str:
    """A .sql file is already text; no grid, no sheet, nothing to flatten."""
    return Path(path).read_text(errors="ignore")


def declared_view(text: str):
    """(view name, [declared columns]) from the CREATE VIEW header.

    The header is the completeness anchor for SQL: a spreadsheet says how many
    rows it has, a view says how many columns it declares. Returns (None, [])
    when no header is recognisable, and the caller then reports the record
    count without judging it.
    """
    match = VIEW_HEADER.search(text)
    if not match:
        return None, []
    return match.group(1).strip('"'), re.findall(r'"([^"]+)"', match.group(2))


def expected_column_count(text: str):
    columns = declared_view(text)[1]
    return len(columns) or None
