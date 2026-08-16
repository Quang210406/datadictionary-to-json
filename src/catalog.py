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

from pathlib import Path

import pandas as pd

from layout import DEFAULT_LAYOUT, hop_dirs, stages_of_dir


def _table_of(path: Path, non_hop_sheets) -> tuple:
    """(table name, sheet name) for one hop workbook.

    The first sheet is named after the table it targets, which is more
    reliable than the file name ("DWH_TEMP_CLIENT v2.xlsx" holds sheet
    "DWH_TEMP_CLIENT"). Falls back to the file stem if a sheet is unnamed.
    """
    try:
        sheets = pd.ExcelFile(path).sheet_names
    except Exception:
        return None, None
    for sheet in sheets:
        if sheet.strip().upper() not in non_hop_sheets:
            return sheet.strip().upper(), sheet
    return path.stem.strip().upper(), sheets[0]


def build_catalog(archive_dir, layout=None) -> dict:
    """{TABLE -> {"path", "sheet", "stage_dir"}} for every hop workbook.

    A file whose NAME matches the table always wins over one that merely
    contains a sheet of that name: some workbooks carry a copy-pasted sheet
    title from another table (STG_CARD_CREDIT_CARD_INFO.xlsx has a sheet
    called STG_FDM_TRAN_HIS), and resolving through those would silently
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
            table, sheet = _table_of(path, non_hop_sheets)
            if not table:
                continue
            # The stage names are stamped on here, so assembly reads them off
            # the entry instead of consulting a table of folder names.
            from_stage, to_stage = stages_of_dir(layout, stage_dir)
            entry = {"path": str(path), "sheet": sheet, "stage_dir": stage_dir,
                     "from_stage": from_stage, "to_stage": to_stage}
            # A file name may carry a version suffix the sheet does not
            # ("STG_MDM_CIF_ADDRESS_v1_20240530.xlsx" holds STG_MDM_CIF_ADDRESS).
            stem = path.stem.strip().upper()
            authoritative = stem == table or stem.startswith(table + "_V")
            if authoritative or table not in catalog:
                if authoritative or not catalog.get(table, {}).get("authoritative"):
                    catalog[table] = {**entry, "authoritative": authoritative}
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
