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

# The reference workbook holds the final (cloud) stage: one sheet per table,
# rather than one file per table like the hop specs.
CLOUD_GLOB = "*Mapping*CLOUD*.xlsx"
HOP_DIRS = ("SRC_STGDIH", "STGDIH_DWHDIH")

# Sheets in a hop workbook that are not the hop itself.
NON_HOP_SHEETS = {"DDL"}


def _table_of(path: Path) -> tuple:
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
        if sheet.strip().upper() not in NON_HOP_SHEETS:
            return sheet.strip().upper(), sheet
    return path.stem.strip().upper(), sheets[0]


def build_catalog(archive_dir) -> dict:
    """{TABLE -> {"path", "sheet", "stage_dir"}} for every hop workbook.

    A file whose NAME matches the table always wins over one that merely
    contains a sheet of that name: some workbooks carry a copy-pasted sheet
    title from another table (STG_CARD_CREDIT_CARD_INFO.xlsx has a sheet
    called STG_FDM_TRAN_HIS), and resolving through those would silently
    read the wrong table's mappings.
    """
    archive = Path(archive_dir)
    catalog = {}
    for stage_dir in HOP_DIRS:
        folder = archive / stage_dir
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.xlsx")):
            if path.name.startswith("~$"):
                continue
            table, sheet = _table_of(path)
            if not table:
                continue
            entry = {"path": str(path), "sheet": sheet, "stage_dir": stage_dir}
            # A file name may carry a version suffix the sheet does not
            # ("STG_MDM_CIF_ADDRESS_v1_20240530.xlsx" holds STG_MDM_CIF_ADDRESS).
            stem = path.stem.strip().upper()
            authoritative = stem == table or stem.startswith(table + "_V")
            if authoritative or table not in catalog:
                if authoritative or not catalog.get(table, {}).get("authoritative"):
                    catalog[table] = {**entry, "authoritative": authoritative}
    return catalog


def find_cloud_workbook(archive_dir):
    """The hand-built DWH->CLOUD mapping, or None when it is absent."""
    matches = sorted(Path(archive_dir).glob(CLOUD_GLOB))
    return str(matches[0]) if matches else None


def cloud_sheets(cloud_path) -> dict:
    """{TABLE -> sheet name} for the cloud workbook's per-table sheets."""
    if not cloud_path:
        return {}
    return {s.strip().upper(): s for s in pd.ExcelFile(cloud_path).sheet_names}
