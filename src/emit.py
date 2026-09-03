"""Write the assembled dictionary in the hand-built layout.

The JSON is the machine artefact; this is the one a person opens next to the
manual sheet and compares row by row. Same four stage groups, same tail
columns, same order.
"""

import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import descriptions
from assemble import produced_entry, short_path, stages_in

# Fill colour per stage group, taken by the stage's POSITION in the pipeline
# rather than by its name. This was the last place downstream of assembly that
# still knew the stage names of one particular archive; everything else reads
# the stage list off the records (assemble.stages_in).
#
# The palette is the old name-to-colour table in pipeline order, so any archive
# whose stages run source -> staging -> dwh -> cloud emits exactly the fills it
# did before: those four colours already WERE PALETTE[0..3], in that order.
#
# What the hardcoded names actually cost was not a missing colour — an
# unrecognised stage already fell back to its position — but a collision
# between the two schemes. The fallback could hand a stage a colour that a
# *named* stage beside it already owned: stages ["warehouse", "source"] shaded
# both groups FFE8D6, two adjacent column groups indistinguishable in the one
# artefact whose whole job is to be read by eye. One scheme cannot contradict
# itself that way. Beyond the palette's length it cycles rather than failing.
PALETTE = ["FFE8D6", "D6E8F5", "DDEEDD", "EADCF0", "F5E6CC", "E0E0F0"]


def stage_groups(stages) -> list:
    """(display name, stage, fill) per stage, in pipeline order."""
    return [(stage.replace("_", " ").title(), stage, PALETTE[i % len(PALETTE)])
            for i, stage in enumerate(stages)]
STAGE_COLS = ["Tên Bảng", "Tên Cột", "Đường Dẫn", "datatype", "size"]
TAIL_COLS = ["Mô Tả", "transformation logic", "Logic Notes", "Join / Depends-on"]
WIDTHS = {1: 22, 2: 22, 3: 46, 4: 11, 5: 7, 6: 26, 7: 24, 8: 46, 9: 11, 10: 7,
          11: 20, 12: 18, 13: 48, 14: 11, 15: 7, 16: 20, 17: 18, 18: 60, 19: 11,
          20: 7, 21: 30, 22: 20, 23: 44, 24: 40}
TABLE_TOKEN = re.compile(r"\b(?:STG|DWH|SRC)_[A-Z0-9_]{3,}\b", re.I)
AUTHORED_COL = descriptions.AUTHORED_COL   # one spelling, declared once


def _write_rows(ws, rows, start_row, should_wrap):
    """Values into cells, formatted as text so Excel cannot reinterpret them.

    Text format matters: without it Excel turns a value like "1-1" into a date,
    which silently corrupts a dictionary.
    """
    for r, row in enumerate(rows, start=start_row):
        for c, value in enumerate(row, start=1):
            cell = ws.cell(r, c, value if value not in ("", None) else None)
            cell.alignment = Alignment(vertical="top", wrap_text=should_wrap(c))
            if isinstance(value, str):
                cell.number_format = "@"


def _apply_layout(ws, widths, freeze):
    for c, width in widths.items():
        ws.column_dimensions[get_column_letter(c)].width = width
    ws.freeze_panes = freeze


def _tail(record, authored=None):
    """(description, transformation type, rule, dependencies) for one row.

    `authored` is appended as a FIFTH value when a description overlay is in
    play, never merged into the first. The two are different kinds of claim —
    one copied from a document and checkable against it, the other somebody's
    reading — and one column holding both would make that difference
    unrecoverable for whoever reads the sheet next.
    """
    produced = None
    for entry in record["lineage"]:
        if entry["sources"]:
            produced = entry
    source = produced["sources"][0] if produced and produced["sources"] else {}
    logic = source.get("transformation_logic") or ""
    named = {t.upper() for t in TABLE_TOKEN.findall(logic)}
    named -= {(source.get("table") or "").upper()}
    tail = (record.get("description"), source.get("transformation_type"),
            logic or None, ", ".join(sorted(named)) or None)
    return tail if authored is None else tail + (authored or None,)


def to_rows(lineage_records, groups, overlay=None) -> list:
    rows = []
    for record in lineage_records:
        by_stage = {e["stage"]: e for e in record["lineage"]}
        row = []
        for _, stage, _ in groups:
            entry = by_stage.get(stage)
            row += ([entry["table"], entry["column"], short_path(entry["offline_path"]),
                     entry["datatype"], entry["size"]] if entry else [None] * 5)
        authored = None if overlay is None else (
            descriptions.authored_for(record, overlay) or "")
        rows.append(row + list(_tail(record, authored)))
    return rows


def write_workbook(lineage_records, path, stages=None, overlay=None):
    """The archive spreadsheet. `overlay` adds one column and changes nothing
    else — without it the layout is byte-for-byte what it has always been."""
    tail_cols = TAIL_COLS if overlay is None else TAIL_COLS + [AUTHORED_COL]
    groups = stage_groups(stages or stages_in(lineage_records))
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for i, (name, _, color) in enumerate(groups):
        off = i * 5
        ws.cell(2, off + 1, name)
        fill = PatternFill("solid", fgColor=color)
        for k, header in enumerate(STAGE_COLS):
            ws.cell(3, off + k + 1, header)
            ws.cell(2, off + k + 1).fill = fill
            ws.cell(3, off + k + 1).fill = fill
            ws.cell(3, off + k + 1).font = Font(bold=True)
        ws.cell(2, off + 1).font = Font(bold=True)
    tail_start = len(groups) * len(STAGE_COLS) + 1
    for k, header in enumerate(tail_cols):
        cell = ws.cell(3, tail_start + k, header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="EEEEEE")
    _write_rows(ws, to_rows(lineage_records, groups, overlay), 4,
                lambda c: c >= tail_start)
    widths = dict(WIDTHS)
    if overlay is not None:
        widths[tail_start + len(tail_cols) - 1] = 60
    _apply_layout(ws, widths, "A4")
    wb.save(path)
    return path


# ------------------------------------------------------- SQL view workbook
#
# Views carry no datatype or size, and only two stages, so they get their own
# column layout rather than a squeezed version of the four-stage one. Matches
# the hand-built SQL ground truth column for column.

VIEW_COLS = ["Source Schema", "Source Table", "Source Column", "View Name",
             "View Column", "Role", "Transformation", "Đường dẫn", "Alias",
             "Ultimate Source", "Via"]
VIEW_WIDTHS = {1: 14, 2: 26, 3: 30, 4: 26, 5: 30, 6: 9, 7: 62, 8: 26, 9: 10,
               10: 30, 11: 34}


def view_rows(view_records) -> list:
    rows = []
    for record in view_records:
        # By position, not by the stage name "view": a record produced by a
        # statement of any other kind would miss a name lookup, and the miss
        # would render as two blank cells under View Name / View Column rather
        # than as an error — a wrong dictionary that looks merely incomplete.
        view = produced_entry(record) or {}
        source = (view.get("sources") or [{}])[0]
        resolved = record.get("resolved_source") or {}
        ultimate = ""
        if resolved.get("column"):
            ultimate = ".".join(x for x in (resolved.get("table"),
                                            resolved.get("column")) if x)
        rows.append([
            source.get("schema"), source.get("table"), source.get("column"),
            view.get("table"), view.get("column"), source.get("role"),
            source.get("transformation_logic"),
            Path(view.get("offline_path") or "").name or None,
            source.get("alias"),
            ultimate or None, " -> ".join(resolved.get("via", [])) or None,
        ])
    return rows


def write_view_workbook(view_records, path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for j, header in enumerate(VIEW_COLS, start=1):
        cell = ws.cell(1, j, header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="EEEEEE")
    _write_rows(ws, view_rows(view_records), 2, lambda c: c == 7)
    _apply_layout(ws, VIEW_WIDTHS, "A2")
    wb.save(path)
    return path
