"""Descriptions written by a person, kept beside the dictionary rather than in it.

Where no source document states a meaning, the field's description is null —
this program copies descriptions, it has never generated one. Filling those in
is human work, and the person doing it is not a developer.

**The descriptions are an overlay, never part of `output.json`.** That file
means one thing: what the documents state. Every value in it can be checked
character-for-character against the single file it came from, and that is the
whole verification story. A sentence somebody wrote cannot be checked that way,
so putting it in the same array would quietly broaden what `output.json`
claims — `validate_assembled` would still print "N/N records clean" over a
dictionary that is now part testimony, and `with_description` would read 100%
forever, deleting a real measurement by making it tautological.

So the two stay separate and are joined at write time, into the spreadsheet a
human reads. That is the project's governing principle one level up: two
separately checkable inputs, one deterministic join.

The unit matters. One record is one (target field, source field) pair, so a
field with ten sources is ten records — but it has ONE meaning. She writes one
description per FIELD; this module fans it out. Measured on the real archive:
83 records, 70 fields, one of which spans 10 records.
"""

import unicodedata
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from assemble import (field_key, short_path, stages_in, target_entry,
                      target_key)

# Her columns. The two description columns sit side by side on purpose: one
# holds what a document said, the other what she wrote. Nobody has to invent a
# precedence rule, and a reader can see which is which without being told.
TABLE_COL = "Bảng"
COLUMN_COL = "Cột"
STAGE_COL = "Stage"
EVIDENCE_COL = "Đường dẫn bằng chứng"
DOCUMENT_COL = "Mô Tả (tài liệu)"
AUTHORED_COL = "Mô Tả (bổ sung)"
# Where a supplementary description came from. Blank means a person wrote it;
# otherwise it names the document and the section it was extracted from.
#
# This column is what keeps three different kinds of claim distinguishable in
# one sheet: a mapping sheet stated it (DOCUMENT_COL), a prose document stated
# it and a model read it out (AUTHORED_COL with a source), or a person wrote it
# (AUTHORED_COL with none). The first is checkable against a grid, the second
# against a page, the third against nobody — and a reader has to be able to
# tell which they are looking at.
SOURCE_COL = "Nguồn"
TEMPLATE_COLS = [TABLE_COL, COLUMN_COL, STAGE_COL, EVIDENCE_COL,
                 DOCUMENT_COL, AUTHORED_COL, SOURCE_COL]

# The stage list the file was written against, parked on its own sheet. See
# _check_layout below for why this is not optional bookkeeping.
META_SHEET = "_meta"
META_STAGES = "stages"

WIDTHS = {1: 26, 2: 26, 3: 12, 4: 52, 5: 60, 6: 60, 7: 46}


def _clean(value) -> str:
    """One cell, as a string a human may have typed into Excel.

    Three hazards, all routine rather than exotic:

      * a non-breaking space, which is what arrives when Vietnamese text is
        pasted from Word or a browser, and which is not `str.strip()`-able
      * NFD vs NFC — the same Vietnamese word can be stored as a base letter
        plus a combining diacritic, or as one precomposed character. They look
        identical and compare unequal, which would silently orphan a row.
      * numbers, dates and booleans, because openpyxl returns cell values in
        whatever type Excel decided they were
    """
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value))
    # Written as an escape, not the literal character: an invisible NBSP in
    # source is one careless reformat away from becoming a plain space, and
    # the bug it causes is a row that silently refuses to match.
    return text.replace("\u00a0", " ").strip()


def field_rows(records) -> list:
    """One row per distinct target field, in first-seen order.

    Keyed on `field_key(*target_key(record))` — normalised — because Excel is
    the round-trip medium and a human retyping a cell will not reproduce the
    source's padding or casing. The row still DISPLAYS the exact spelling, so
    the sheet shows what the dictionary says.
    """
    rows, exact = {}, set()
    for record in records:
        key = target_key(record)
        if key is None:
            continue
        exact.add(key)
        match = field_key(*key)
        row = rows.get(match)
        if row is None:
            entry = target_entry(record) or {}
            row = rows[match] = {
                "key": match,
                TABLE_COL: key[0] or "",
                COLUMN_COL: key[1] or "",
                STAGE_COL: entry.get("stage") or "",
                # Shortened, like the hand-built sheet cites evidence.
                # The raw value is absolute, so writing it here would
                # send a reviewer's home directory to whoever opens
                # this file — and this file is made to be sent.
                EVIDENCE_COL: short_path(entry.get("offline_path")) or "",
                DOCUMENT_COL: "",
                "records": 0,
            }
        row["records"] += 1
        if not row[DOCUMENT_COL] and record.get("description"):
            row[DOCUMENT_COL] = record["description"]

    # Normalising to match is only safe while it merges nothing. If two fields
    # the dictionary reports separately ever fold into one row, she would
    # describe one and silently lose the other — so refuse to write the file
    # rather than hand her a lossy one. Today: 70 and 70.
    if len(exact) != len(rows):
        collapsed = len(exact) - len(rows)
        raise ValueError(
            f"{collapsed} field(s) differ only by case or padding and would "
            f"share one row ({len(exact)} distinct fields, {len(rows)} rows). "
            "Refusing to export a template that cannot round-trip.")
    return list(rows.values())


def export_template(records, path, stages=None, prefill=None):
    """Write the sheet a person fills in.

    `prefill` is {normalised key -> (text, source)} — descriptions a model read
    out of a prose document. They land in the SAME column a person writes in,
    because they are the same kind of claim about meaning, with the source
    named beside them so nobody has to guess which is which. A reviewer edits
    or deletes them exactly like their own text.
    """
    rows = field_rows(records)
    stages = list(stages or stages_in(records))
    for row in rows:
        text, source = (prefill or {}).get(row["key"], (None, None))
        if text:
            row[AUTHORED_COL] = text
            row[SOURCE_COL] = source or ""

    wb = Workbook()
    ws = wb.active
    ws.title = "Descriptions"
    for i, header in enumerate(TEMPLATE_COLS, start=1):
        cell = ws.cell(1, i, header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="EEEEEE")
    for r, row in enumerate(rows, start=2):
        for c, header in enumerate(TEMPLATE_COLS, start=1):
            cell = ws.cell(r, c, row.get(header) or None)
            cell.alignment = Alignment(vertical="top",
                                       wrap_text=header in (DOCUMENT_COL,
                                                            AUTHORED_COL))
            cell.number_format = "@"
    for c, width in WIDTHS.items():
        ws.column_dimensions[get_column_letter(c)].width = width
    ws.freeze_panes = "A2"

    meta = wb.create_sheet(META_SHEET)
    meta["A1"] = META_STAGES
    meta["B1"] = ",".join(stages)
    meta.sheet_state = "hidden"

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path, len(rows)


class Overlay:
    """What a person wrote, keyed by normalised field."""

    def __init__(self, entries, stages, source, sources=None):
        self.entries = entries      # {normalised key -> text}
        self.stages = stages        # the stage list it was written against
        self.source = source        # the file this overlay was read from
        # {key -> where that description came from}. Empty string means a
        # person wrote it; a document name and section means a model read it.
        self.sources = sources or {}

    def __len__(self):
        return len(self.entries)


def _check_layout(found, expected):
    """A key means nothing without the layout that produced it.

    `assemble.target_key` decides which entry names the field by looking for
    the stage literally called "dwh", and skipping one called "cloud" — but
    `layout.py` lets an archive name its stages anything. Under a different
    layout the SAME field keys differently, so every row would orphan at once
    and the report would read as though she had described the wrong things.

    Cheaper to refuse than to fix target_key, which three callers depend on.
    """
    if found and expected and found != expected:
        raise ValueError(
            f"This description file was written against stages {found}, but "
            f"this run has {expected}. The same field keys differently under "
            "the two, so every description would orphan. Re-export the "
            "template for this layout, or run the layout it was written for.")


def load(path, stages=None) -> Overlay:
    """Read her filled-in sheet back."""
    wb = load_workbook(path, data_only=True)
    ws = wb["Descriptions"] if "Descriptions" in wb.sheetnames else wb.worksheets[0]

    header = [_clean(c.value) for c in ws[1]]
    try:
        table_at = header.index(TABLE_COL)
        column_at = header.index(COLUMN_COL)
        authored_at = header.index(AUTHORED_COL)
    except ValueError:
        raise ValueError(
            f"{Path(path).name} is missing one of the required columns "
            f"{[TABLE_COL, COLUMN_COL, AUTHORED_COL]}; found {header}.") from None

    found_stages = []
    if META_SHEET in wb.sheetnames:
        meta = wb[META_SHEET]
        if _clean(meta["A1"].value) == META_STAGES:
            found_stages = [s for s in _clean(meta["B1"].value).split(",") if s]
    _check_layout(found_stages, list(stages) if stages else [])

    source_at = header.index(SOURCE_COL) if SOURCE_COL in header else None
    entries, sources = {}, {}
    for row in ws.iter_rows(min_row=2):
        cells = [_clean(c.value) for c in row]
        if len(cells) <= max(table_at, column_at, authored_at):
            continue
        text = cells[authored_at]
        # Blank means UNFILLED. A spreadsheet cannot express "deliberately no
        # description" distinctly from "not got to it yet", so the sheet header
        # says blank means unfilled and this honours that rather than guessing.
        if not text:
            continue
        key = field_key(cells[table_at], cells[column_at])
        if key is not None:
            entries[key] = text
            if source_at is not None and source_at < len(cells):
                sources[key] = cells[source_at]
    return Overlay(entries, found_stages, str(path), sources)


def merge_report(records, overlay) -> dict:
    """Which descriptions landed, which found no field, which field has none.

    Rows are matched by KEY, never by position — she will sort and filter the
    sheet, and a position-matched load would then attach descriptions to the
    wrong fields while reporting a perfect score.
    """
    rows = field_rows(records)
    by_key = {row["key"]: row for row in rows}

    matched, undescribed = [], []
    for row in rows:
        authored = overlay.entries.get(row["key"])
        if authored:
            matched.append(row["key"])
        elif not row[DOCUMENT_COL]:
            undescribed.append(row["key"])

    # An orphan is never deleted. A renamed table orphans every one of its
    # descriptions at once, and her work is recoverable by hand only while the
    # text is still in the file.
    orphaned = [key for key in overlay.entries if key not in by_key]

    render = lambda key: f"{key[0]}.{key[1]}" if key[0] else key[1]
    from_docs = sum(1 for k in matched if (overlay.sources.get(k) or "").strip())
    return {
        "source": overlay.source,
        "fields": len(rows),
        "matched": len(matched),
        "from_documents": from_docs,
        "from_people": len(matched) - from_docs,
        "orphaned": len(orphaned),
        "undescribed": len(undescribed),
        "orphaned_keys": [render(k) for k in sorted(orphaned)],
        "undescribed_keys": [render(k) for k in sorted(undescribed)],
    }


def authored_for(record, overlay):
    """The authored description for this record's field, or None.

    One field, one meaning: every record sharing a target field gets the same
    sentence, which is what makes writing 70 descriptions cover 83 records.
    """
    if overlay is None:
        return None
    key = target_key(record)
    if key is None:
        return None
    return overlay.entries.get(field_key(*key))


# ------------------------------------------------- descriptions from prose
#
# The bridge the whole exercise is aimed at: a design document states what a
# field MEANS, and that meaning has to reach the entity a person reads.
#
# It is a join, not an extraction. The model reads ONE document and says
# "column X means Y, found in section Z" — it is never shown the dictionary, so
# it cannot be led into agreeing with it. Matching those statements to real
# fields happens here, in plain Python, by the same key everything else uses.
# That is the governing principle applied to meanings rather than to lineage.

DOC_KIND = "doc_prose"


def from_documents(records, store, paths) -> tuple:
    """Read prose documents for field meanings; return (prefill, report).

    prefill is {field key -> (description, source)} for meanings that match a
    field this dictionary actually has. Everything else is reported rather than
    dropped: a design document describes the whole system, so most of what it
    says is about fields this run did not build, and that is not an error.
    """
    known = {row["key"] for row in field_rows(records)}
    prefill, unmatched, read = {}, [], []

    for path in paths:
        name = Path(path).name
        found = store.records(str(path), None, DOC_KIND)
        read.append({"file": name, "definitions": len(found)})
        for item in found:
            column = (item.get("column") or "").strip()
            if not column:
                continue
            description = (item.get("description") or "").strip()
            if not description:
                continue
            section = (item.get("section") or "").strip()
            where = f"{name}" + (f" — {section}" if section else "")
            key = field_key(item.get("table"), column)
            if key is None:
                continue
            if key in known:
                # First document to describe a field wins; a later one does not
                # silently overwrite it, because there would be no way to tell
                # afterwards which document was believed.
                prefill.setdefault(key, (description, where))
            else:
                unmatched.append({
                    "table": item.get("table"), "column": column,
                    "section": section, "file": name})

    return prefill, {
        "documents_read": read,
        "definitions_matched": len(prefill),
        "definitions_unmatched": len(unmatched),
        "unmatched_examples": [
            f"{u['table'] or '?'}.{u['column']} ({u['file']})"
            for u in unmatched[:DIAGNOSTIC_EXAMPLES]],
    }


DIAGNOSTIC_EXAMPLES = 5
