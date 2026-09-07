"""One mapping claim, whatever kind of file stated it.

Every lineage-producing source says the same thing in a different dialect: THIS
column of THIS object is loaded from THAT column of THAT object, like so. A hop
specification says it in a spreadsheet row, a CREATE statement says it in a
SELECT list, a design document says it in a table inside prose. Three dialects,
one claim.

This module is where the dialects converge. It is deliberately the ONLY place
they converge — `templates.py` keeps a separate extraction contract per kind,
because both SQL models set `extra: forbid` and emit every field as required, so
a union contract would add always-null keys to the SQL prompt and silently
re-measure a set of published numbers. Unify at the assembler's internal shape;
never at the contract.

## The subject, and why it is stamped here

`assemble._walk_back` joins the table half of a key through the catalog and the
column half by string compare. That looks like an inconsistency and is actually
a repair: the per-row "Target Table Name" cell is *known wrong on every row* of
real hop workbooks — STG_TXN_HISTORY.xlsx labels every row "TXN_HISTORY", the
SOURCE table, copied down the column. The catalog is not a file index. It is the
mechanism that replaces that cell with the sheet name.

A global pool of claims would make that distrusted cell the join key, which is
the trap that has stopped this rewrite before. The way through is that the
repair was never a property of the *walk*. It is a property of knowing what a
file is ABOUT, and `assemble.resolve_table` already computes exactly that, in
one line, before it walks anything:

    owner_table = (owner.get("sheet") or "").strip() or target_table

So: resolve one SUBJECT per file, deterministically, in Python, from a fact the
file's structure states rather than from a cell a model read. Stamp it on every
claim that file produced. Only then pool them. The distrusted cell never becomes
a join key, and no prompt changes — which matters more than it looks, because
cache keys are file content and kind and never the prompt, so a prompt change
would keep serving old answers until someone noticed months later.

`doc_lineage` is the exception and is marked as one. A mapping table inside a
PDF has no sheet name and no CREATE statement, so its subject IS the model's
stated `target_table`. That claim carries `subject_trusted=False` and the report
says how many such claims a dictionary rests on. It is not hidden behind the
merge: a reviewer is entitled to know which half of a chain stands on a file
fact and which on a sentence.
"""

from dataclasses import dataclass, replace
from typing import Optional

import kinds

# `cloud_sheet` is deliberately absent from the normalisers below: it describes
# one table's columns as they land, which is column DETAIL, not a claim that one
# field is loaded from another. It stays an index (assemble.build_cloud_index)
# rather than becoming a degenerate claim with no source half.


@dataclass(frozen=True)
class Claim:
    """One (source field -> subject field) assertion, and the evidence for it.

    Every field is optional but `target_column`, which is the join key and the
    one value an extraction may not return null — the same rule the per-kind
    contracts already enforce, restated here because this is the shape the
    assembler actually joins on.

    Datatypes appear at both ends because a hop spec states both and they differ
    across a hop in about a tenth of rows. SQL states neither: a view declares no
    types, and a CTAS inherits them from its SELECT. Those arrive as None rather
    than being invented.
    """

    # Stamped by Python from the file's structure — see the module docstring.
    subject_table: Optional[str]
    subject_trusted: bool
    target_column: str

    source_schema: Optional[str]
    source_table: Optional[str]
    source_column: Optional[str]
    source_alias: Optional[str]
    source_role: Optional[str]

    transformation_type: Optional[str]
    transformation_logic: Optional[str]

    target_datatype: Optional[str]
    target_size: Optional[str]
    source_datatype: Optional[str]
    source_size: Optional[str]

    # Where this claim was read from. `evidence_path` is the file; the section is
    # the sheet for a workbook, None for a .sql file (which has no parts), and
    # the heading for a document. It is what makes a claim checkable: every
    # string above can be found in that one place.
    evidence_path: Optional[str]
    evidence_section: Optional[str]
    kind: str
    # Position within its own file, preserved so a pooled ordering can stay
    # deterministic — see `ordered` below.
    ordinal: int


def _text(value):
    """One extracted cell as a string, or None.

    Extractions arrive as JSON, so a value may be a number or a bool where the
    source held one. Everything downstream compares and writes strings.
    """
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    return text or None


# ------------------------------------------------------------- per kind
#
# One normaliser per dialect. Each takes the raw extraction records for ONE file
# (or one sheet, or one section) plus the subject Python resolved for it, and
# returns Claims. The differences between them are exactly the differences
# between the contracts, written out once, here, instead of being spread through
# the assembler as `record.get(...)` calls that happen to name different keys.


def _from_hop(record, subject, path, section, ordinal) -> Optional[Claim]:
    """A hop specification row: two stages, types at both ends.

    `record["target_table"]` is READ AND DISCARDED on purpose. It is the cell the
    module docstring describes, and the subject argument is its replacement.
    """
    column = _text(record.get("target_column"))
    if not column:
        return None
    return Claim(
        subject_table=subject, subject_trusted=True, target_column=column,
        source_schema=None,
        source_table=_text(record.get("source_table")),
        source_column=_text(record.get("source_column")),
        source_alias=None,
        source_role=_text(record.get("source_role")) or "value",
        transformation_type=_text(record.get("transformation_type")),
        transformation_logic=_text(record.get("transformation_logic")),
        target_datatype=_text(record.get("target_datatype")),
        target_size=_text(record.get("target_size")),
        source_datatype=_text(record.get("source_datatype")),
        source_size=_text(record.get("source_size")),
        evidence_path=path, evidence_section=section, kind="hop_spec",
        ordinal=ordinal)


def _from_sql(record, subject, path, section, ordinal, kind) -> Optional[Claim]:
    """One (declared column, source field) pair of a CREATE statement."""
    column = _text(record.get("target_column"))
    if not column:
        return None
    return Claim(
        subject_table=subject, subject_trusted=True, target_column=column,
        source_schema=_text(record.get("source_schema")),
        source_table=_text(record.get("source_table")),
        source_column=_text(record.get("source_column")),
        source_alias=_text(record.get("source_alias")),
        source_role=_text(record.get("source_role")) or "value",
        # A view states no transformation TYPE — only the expression itself.
        # Left None rather than filled with a guess like "Direct Mapping".
        transformation_type=None,
        transformation_logic=_text(record.get("transformation_logic")),
        target_datatype=None, target_size=None,
        source_datatype=None, source_size=None,
        evidence_path=path, evidence_section=section, kind=kind,
        ordinal=ordinal)


def _from_doc(record, subject, path, section, ordinal) -> Optional[Claim]:
    """A mapping a prose document states.

    The one kind whose subject cannot come from structure. `subject` is passed in
    as None by the caller and the record's own `target_table` fills it, with
    `subject_trusted=False` recording that this claim rests on a cell.
    """
    column = _text(record.get("target_column"))
    if not column:
        return None
    stated = _text(record.get("target_table"))
    return Claim(
        subject_table=subject or stated, subject_trusted=False,
        target_column=column,
        source_schema=None,
        source_table=_text(record.get("source_table")),
        source_column=_text(record.get("source_column")),
        source_alias=None,
        source_role=_text(record.get("source_role")) or "value",
        transformation_type=None,
        transformation_logic=_text(record.get("transformation_logic")),
        target_datatype=None, target_size=None,
        source_datatype=None, source_size=None,
        evidence_path=path,
        # A document's own stated section beats the caller's, when it gave one:
        # the model was asked where in the document it found the definition, and
        # that is finer-grained than the chunk the text was cut into.
        evidence_section=_text(record.get("section")) or section,
        kind="doc_lineage", ordinal=ordinal)


# One normaliser per dialect, and the dialects a build actually speaks are
# whichever of these `kinds.py` registers. That indirection is the same one
# `readers.py` uses for formats: a normaliser declared here becomes live the
# moment its kind is registered, with no second edit and no list to keep in
# step. `doc_lineage` is written and waiting on exactly that.
_NORMALISERS = {
    "hop_spec": lambda r, s, p, sec, i: _from_hop(r, s, p, sec, i),
    "view_sql": lambda r, s, p, sec, i: _from_sql(r, s, p, sec, i, "view_sql"),
    "table_sql": lambda r, s, p, sec, i: _from_sql(r, s, p, sec, i, "table_sql"),
    "doc_lineage": lambda r, s, p, sec, i: _from_doc(r, s, p, sec, i),
}

# The kinds that state a mapping AND are registered. Computed rather than
# written out, so it cannot fall behind the registry the way four hand-kept
# dicts once did.
LINEAGE_KINDS = tuple(k for k in _NORMALISERS if k in kinds.KINDS)


def claims_from(kind, path, section, subject, records) -> list:
    """Claims for ONE file (or sheet, or section), subject already resolved.

    Raises on a kind that states no mapping rather than returning nothing. A
    kind that produces no claims and does not say so is the failure mode this
    codebase keeps rediscovering: it does not fail, it quietly empties a
    dictionary and every check still passes.
    """
    normalise = _NORMALISERS.get(kind) if kind in LINEAGE_KINDS else None
    if normalise is None:
        raise ValueError(
            f"{kind!r} states no mapping claims; expected one of "
            f"{list(LINEAGE_KINDS)}. `cloud_sheet` is column detail and is "
            "indexed, not claimed — see assemble.build_cloud_index.")

    out = []
    for ordinal, record in enumerate(records):
        if not isinstance(record, dict):
            continue        # the shape check already reported this
        claim = normalise(record, subject, path, section, ordinal)
        if claim is not None:
            out.append(claim)
    return out


# ------------------------------------------------------------- the pool


def ordered(claims) -> list:
    """Claims in a defined order, so "the first match" means something.

    Today "take the first mapping upstream" (`assemble._walk_back`, `matches[0]`)
    is deterministic for free, because the candidates all come from one file and
    keep that file's row order. Pool them globally and "first" silently becomes
    directory iteration order — a result that can change between machines while
    every check still passes.

    Sorting on (evidence, position within that evidence) preserves exactly
    today's answer wherever one file owns a subject, which is every case in the
    real archive, and defines an answer for the case where several files claim
    one field.
    """
    return sorted(claims, key=lambda c: (c.evidence_path or "",
                                         c.evidence_section or "",
                                         c.ordinal))


def index_by_produced(claims, field_key) -> dict:
    """{(SUBJECT, COLUMN) -> [claims]}, the join index the assembler walks.

    Keyed on the FULL field key, not the column alone. `assemble._match` scopes
    to one file's records and so cannot confuse two tables that share a column
    called `ID`; a global pool has no such luck, and would. The key restores that
    scoping explicitly — and it is the key `_walk_back` already computes at its
    top and then spends only on the cycle set, because until the subject was
    trustworthy the table half was not safe to join on.
    """
    index = {}
    for claim in ordered(claims):
        key = field_key(claim.subject_table, claim.target_column)
        if key is not None:
            index.setdefault(key, []).append(claim)
    return index


def fan_in(index) -> list:
    """Fields upstream of which more than one claim was stated.

    `matches[0]` keeps the nearest source line and today's chain diagnostics
    report the rest. Pooling makes that choice wider, so it is surfaced rather
    than absorbed: these are the places where a chain is a tree and the
    dictionary shows one branch of it.
    """
    return [(key, claims) for key, claims in index.items() if len(claims) > 1]


def untrusted(claims) -> list:
    """Claims whose subject came from a cell rather than from a file fact."""
    return [c for c in claims if not c.subject_trusted]


def retarget(claim, subject) -> Claim:
    """The same claim under a corrected subject.

    Used where a subject is only knowable after the pool exists — a document that
    names a table nothing else has heard of, for instance. Frozen, so this
    returns a new claim rather than editing one another part of the run may
    already be holding.
    """
    return replace(claim, subject_table=subject)


def _check():
    """Every lineage kind must be registered, and registered as one.

    `kinds.py` decides which document types exist; this module decides which of
    them state a mapping. Two lists that must agree, with the agreement checked
    rather than assumed — the same arrangement agent.py has with kinds.py, and
    for the same reason: a kind named here but absent there is a normaliser that
    can never run, and a kind absent here is a file type that silently
    contributes no lineage, which is the exact bug this module exists to end.
    """
    if not LINEAGE_KINDS:
        raise ValueError(
            "no registered kind states a mapping claim, so no dictionary could "
            f"ever have lineage. Declared normalisers: {sorted(_NORMALISERS)}; "
            f"registered kinds: {sorted(kinds.KINDS)}.")
    for name in LINEAGE_KINDS:
        kind = kinds.get(name)
        if kind.reader not in kinds.READERS:
            raise ValueError(
                f"lineage kind {name!r} declares reader {kind.reader!r}, which "
                "is not a reader kinds.py knows; its files could never be read.")


_check()
