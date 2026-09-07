"""Which file defines which table.

The corpus stores one workbook PER TABLE, not one per stage: the SRC->STG
hop lives in 74 separate files and STG->DWH in 20 more. So a stage is not a
file you can name on the command line — it is whatever file happens to own
the table you arrived at.

This module builds that index once, so assembly can walk a chain backwards
by looking up table names, exactly the way the mapping was done by hand:
open the file that owns the target, read its source, look that source up,
repeat until no file owns it.
"""

import re
from pathlib import Path

import pandas as pd

# Excel's own default sheet names. Never a table, in any corpus — which is why
# this is here rather than in a layout's `non_hop_sheets`: that list is for
# sheets a PARTICULAR archive uses for something else (its "DDL" tab), and a
# person writing a layout for a new archive should not have to know that Excel
# leaves these lying around.
#
# It matters because reading every sheet rather than only the first is what
# found them. Three appeared the moment that changed, one of them in a
# last-hop workbook — so it would have become a DEFAULT BUILD TARGET and spent
# an API call extracting a blank tab.
DEFAULT_SHEET_NAME = re.compile(r"^(?:sheet|trang)\s*\d+$", re.I)

from layout import DEFAULT_LAYOUT, hop_dirs, stages_of_dir


def tables_of(path: Path, non_hop_sheets) -> list:
    """[(table name, sheet name)] for EVERY hop sheet in one workbook.

    A sheet is named after the table it targets, which is more reliable than
    the file name ("DWH_TEMP_PARTY v2.xlsx" holds sheet "DWH_TEMP_PARTY").
    Falls back to the file stem when the only sheet is unnamed.

    **Every sheet, not just the first.** This used to stop at the first
    non-DDL sheet, which quietly encoded one archive's habit of filing one
    table per workbook as a property of the program. A workbook holding three
    table sheets contributed one table and dropped two — no error, no warning,
    just a dictionary missing two thirds of a file. One workbook per STAGE is
    at least as common a shape as one per table, and the codebase could
    already read it: `cloud_sheets` + `build_cloud_index` do exactly this for
    the final stage. The capability existed, wired to one special case.

    Nothing downstream had to change. `_rows_for`, `resolve_table`,
    `archive_claims` and `mapping.claims_from` were already keyed on
    (path, sheet) rather than on the file alone.
    """
    try:
        sheets = pd.ExcelFile(path).sheet_names
    except Exception:
        return []
    found = [(sheet.strip().upper(), sheet) for sheet in sheets
             if sheet.strip().upper() not in non_hop_sheets
             and not DEFAULT_SHEET_NAME.match(sheet.strip())]
    if found:
        return found
    return [(path.stem.strip().upper(), sheets[0])] if sheets else []


def table_of(path: Path, non_hop_sheets) -> tuple:
    """The first hop sheet of a workbook, or (None, None).

    Kept because a caller that genuinely wants ONE answer should not have to
    decide which of several it means. `survey.py` no longer uses it.
    """
    found = tables_of(path, non_hop_sheets)
    return found[0] if found else (None, None)


def build_catalog(archive_dir, layout=None) -> dict:
    """{TABLE -> {"path", "sheet", "stage_dir"}} for every hop workbook.

    A file whose NAME matches the table always wins over one that merely
    contains a sheet of that name: some workbooks carry a copy-pasted sheet
    title from another table (STG_CARD_ACCOUNT_INFO.xlsx has a sheet
    called STG_TXN_HISTORY), and resolving through those would silently
    read the wrong table's mappings.
    """
    layout = layout or DEFAULT_LAYOUT
    non_hop_sheets = {s.strip().upper() for s in layout.get("non_hop_sheets", [])}
    archive = Path(archive_dir)
    catalog = {}
    for stage_dir in hop_dirs(layout):
        folder = archive / stage_dir
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.xlsx")):
            if path.name.startswith("~$"):
                continue
            for table, sheet in tables_of(path, non_hop_sheets):
                if not table:
                    continue
                # The stage names are stamped on here, so assembly reads them
                # off the entry instead of consulting a table of folder names.
                from_stage, to_stage = stages_of_dir(layout, stage_dir)
                entry = {"path": str(path), "sheet": sheet,
                         "stage_dir": stage_dir,
                         "from_stage": from_stage, "to_stage": to_stage}
                # A file name may carry a version suffix the sheet does not
                # ("STG_MDM_PARTY_ADDR_v1_20240530.xlsx" holds
                # STG_MDM_PARTY_ADDR). A workbook holding SEVERAL tables
                # matches none of its sheets by stem, so it is never
                # authoritative — which is right: a file named after one table
                # is better evidence for that table than a file named after
                # none.
                stem = path.stem.strip().upper()
                authoritative = stem == table or stem.startswith(table + "_V")
                if authoritative or table not in catalog:
                    if authoritative or not catalog.get(table, {}).get(
                            "authoritative"):
                        catalog[table] = {**entry,
                                          "authoritative": authoritative}
    return catalog


def find_cloud_workbook(archive_dir, layout=None):
    """The workbook holding the final stage, or None when it is absent."""
    layout = layout or DEFAULT_LAYOUT
    pattern = (layout.get("cloud") or {}).get("glob")
    if not pattern:
        return None
    matches = sorted(Path(archive_dir).glob(pattern))
    return str(matches[0]) if matches else None


def cloud_sheets(cloud_path) -> dict:
    """{TABLE -> sheet name} for the cloud workbook's per-table sheets."""
    if not cloud_path:
        return {}
    return {s.strip().upper(): s for s in pd.ExcelFile(cloud_path).sheet_names}
