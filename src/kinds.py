"""One definition per source kind — the single place a document type exists.

A *source kind* is a type of document the agent knows how to read. Each kind
used to be declared four times, in four unrelated dicts in four modules, all
keyed by the same bare string:

    agent.PROMPTS           what to tell the model
    main.SCHEMA_FILES       which schema its reply must satisfy
    extract.HEADER_ANCHORS  how to find the completeness anchor
    store.EXCEL_KINDS       which reader turns the file into text

Nothing tied those four together, so adding a kind meant remembering all four,
and forgetting one did not fail. That is the real cost, and it is not
hypothetical: a missing HEADER_ANCHORS entry does not raise. It makes
expected_row_count return None, which switches the completeness check off for
that kind — and completeness is the check that catches a truncated reply. The
omission is invisible in the output; the sheet simply passes.

So one SourceKind below declares everything about one kind, no field has a
default, and `_check()` runs at import. A half-declared kind now stops the
program before it starts instead of degrading quietly in the middle of a
ninety-file run.

The prompt TEXT stays in agent.py — the bodies are long and belong beside the
AI code — but this module owns the wiring, and agent.py asserts at import that
its PROMPTS cover exactly the kinds registered here. That half of the check
lives there rather than here for one reason: this module imports nothing from
the project, which is what lets extract.py read from it without dragging
google-genai in behind it. A leaf module cannot close an import cycle.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

# How a file becomes the text the agent sees. A workbook sheet has to be
# flattened to CSV; a .sql file already is text. That one choice also decides
# the completeness anchor (a row count vs a declared column list) and the
# checkpoint-1 input check, so store.py dispatches all three off it rather
# than off a list of kind names.
EXCEL = "excel"
TEXT = "text"
READERS = (EXCEL, TEXT)

# Words that must appear in *different* cells of a source kind's column-header
# row. Deliberately loose: these sheets are hand-maintained and the exact
# captions vary ("Source column Name", "Column Name", "Field"). One tuple per
# side; each tuple is the alternatives for that side.
Anchors = Tuple[Tuple[str, ...], ...]


@dataclass(frozen=True)
class SourceKind:
    """Everything one document type needs, in one place.

    No field has a default, on purpose. Omitting one is a TypeError at import,
    which is exactly what the four-dict arrangement could not do: it let an
    omission through and degraded a check instead of failing.

    header_anchors is None for a TEXT kind — written out rather than defaulted,
    so the entry states the choice instead of inheriting it.
    """

    name: str
    schema_file: str
    reader: str
    header_anchors: Optional[Anchors]


_REGISTRY = (
    SourceKind(
        name="hop_spec",
        schema_file="hop_record.json",
        reader=EXCEL,
        # Both spellings of each side, because the captions are whatever the
        # author of that workbook typed. An archive written in Vietnamese used
        # to match nothing here, which did not fail the run — it silently
        # switched the completeness check off, which is worse. "field" is
        # included on the target side because "Field Name" is a common target
        # caption; a sheet that says "Source Field" still resolves, since each
        # anchor claims a different cell.
        header_anchors=(("target", "đích", "field"), ("source", "nguồn", "from")),
    ),
    SourceKind(
        name="cloud_sheet",
        schema_file="cloud_record.json",
        reader=EXCEL,
        # Without these the completeness check silently skipped cloud sheets,
        # and a truncated reply (23 records for a 48-row sheet) passed
        # unnoticed.
        header_anchors=(("column", "trường", "cột"),
                        ("type", "length", "kiểu", "độ dài")),
    ),
    SourceKind(
        name="view_sql",
        schema_file="view_record.json",
        reader=TEXT,
        # A view's completeness anchor is the column list it declares, found
        # by extract.declared_view, not by a header row in a grid.
        header_anchors=None,
    ),
)

KINDS = {kind.name: kind for kind in _REGISTRY}


def get(name) -> SourceKind:
    """The kind called `name`, or an error that names what is registered."""
    try:
        return KINDS[name]
    except KeyError:
        raise ValueError(
            f"Unknown source kind {name!r}; registered: {sorted(KINDS)}"
        ) from None


def schema_files() -> dict:
    """{kind name -> schema filename}, for loading the schemas."""
    return {name: kind.schema_file for name, kind in KINDS.items()}


def header_anchors(name):
    """Completeness anchors for an Excel kind; None when it has none.

    None here means "not an Excel kind" — it can no longer mean "somebody
    forgot an entry", because `_check()` refuses to import a registry whose
    EXCEL kind has no anchors. That distinction is the point of the registry:
    the missing-entry case was the one that turned the completeness check off
    without saying so.
    """
    kind = KINDS.get(name)
    return kind.header_anchors if kind else None


def _check():
    """Reject a half-declared registry at import time.

    Every rule below corresponds to a failure that used to be silent, or that
    would otherwise surface only once a run had already reached the file.
    """
    if not KINDS:
        raise ValueError("no source kinds are registered")
    if len(KINDS) != len(_REGISTRY):
        seen, duplicates = set(), set()
        for kind in _REGISTRY:
            if kind.name in seen:
                duplicates.add(kind.name)
            seen.add(kind.name)
        raise ValueError(f"source kind name(s) declared twice: {sorted(duplicates)}")

    for kind in _REGISTRY:
        if not kind.name:
            raise ValueError("a source kind has an empty name")
        if not kind.schema_file:
            raise ValueError(f"source kind {kind.name!r} declares no schema_file")
        if kind.reader not in READERS:
            raise ValueError(
                f"source kind {kind.name!r} has reader {kind.reader!r}; "
                f"expected one of {list(READERS)}")

        if kind.reader == EXCEL and not kind.header_anchors:
            raise ValueError(
                f"source kind {kind.name!r} reads Excel but declares no "
                "header_anchors. Without them expected_row_count returns None, "
                "which switches the completeness check off for this kind "
                "instead of failing — the exact omission this registry exists "
                "to prevent.")
        if kind.reader == TEXT and kind.header_anchors:
            raise ValueError(
                f"source kind {kind.name!r} reads text but declares "
                "header_anchors; a text source has no header row to find them "
                "in, so they would never be consulted.")

        for group in kind.header_anchors or ():
            if not group:
                raise ValueError(
                    f"source kind {kind.name!r} has an empty anchor group; it "
                    "could never match a cell, so no header row would be found.")
            for word in group:
                # _is_header_row lower-cases the cells before matching, so an
                # anchor carrying a capital could never match anything. That
                # fails by finding no header row — silently, again.
                if word != word.lower():
                    raise ValueError(
                        f"source kind {kind.name!r} anchor {word!r} is not "
                        "lower-case; header cells are lower-cased before "
                        "matching, so it would never match.")


_check()
