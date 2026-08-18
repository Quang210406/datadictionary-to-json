"""What shape is this archive?

Folder names, the cloud workbook's filename, the stage names and their order
are properties of a particular archive, not of the program. Keeping them here
means a differently-organised archive needs a config file rather than a code
change — and, more importantly, that a *slightly* different archive fails with
a clear message instead of quietly producing wrong stage labels.

Resolution order:
  1. an explicit --layout FILE
  2. archive.json sitting inside the archive folder
  3. DEFAULT_LAYOUT below

The default describes the archive this program was written against, so
existing runs need no config at all.
"""

import json
from pathlib import Path

CONFIG_NAME = "archive.json"

DEFAULT_LAYOUT = {
    # Every stage a field passes through, in pipeline order.
    "stages": ["source", "staging", "dwh", "cloud"],

    # One folder per stage transition. Each folder holds one workbook per
    # table, and the folder says which two stages its files map between.
    "hops": [
        {"dir": "SRC_STGDIH", "from": "source", "to": "staging"},
        {"dir": "STGDIH_DWHDIH", "from": "staging", "to": "dwh"},
    ],

    # The final stage comes from a single workbook with one sheet per table,
    # rather than one file per table like the hops.
    "cloud": {
        "glob": "*Mapping*CLOUD*.xlsx",
        "stage": "cloud",
        # A cloud sheet may file a table without its warehouse prefix:
        # DWH_TXN_HISTORY appears as TXN_HISTORY. Try each prefix stripped.
        "table_prefixes": ["DWH_"],
    },

    # Sheets inside a hop workbook that are not the hop specification.
    "non_hop_sheets": ["DDL"],
}


class LayoutError(ValueError):
    """The archive layout is unusable — raised instead of guessing."""


def load_layout(archive_dir=None, path=None) -> dict:
    if path:
        source = Path(path)
    elif archive_dir and (Path(archive_dir) / CONFIG_NAME).exists():
        source = Path(archive_dir) / CONFIG_NAME
    else:
        return validate_layout(DEFAULT_LAYOUT)
    return validate_layout(json.loads(source.read_text(encoding="utf-8")))


def validate_layout(layout: dict) -> dict:
    """Fail loudly on a layout that cannot describe a pipeline.

    Every stage a hop names must exist in `stages`, or assembly would emit
    labels nothing else recognises — the sort of mistake that otherwise shows
    up as a quietly empty column in the spreadsheet.
    """
    stages = layout.get("stages") or []
    hops = layout.get("hops") or []
    if not stages:
        raise LayoutError("layout has no 'stages'")
    if not hops:
        raise LayoutError("layout has no 'hops'")

    known = set(stages)
    for hop in hops:
        missing = {hop.get("from"), hop.get("to")} - known
        if None in {hop.get("from"), hop.get("to")} or missing:
            raise LayoutError(
                f"hop {hop.get('dir')!r} names stage(s) {sorted(m for m in missing if m)} "
                f"that are not in stages {stages}")
        if not hop.get("dir"):
            raise LayoutError(f"hop {hop} has no 'dir'")

    cloud = layout.get("cloud") or {}
    if cloud and cloud.get("stage") and cloud["stage"] not in known:
        raise LayoutError(f"cloud stage {cloud['stage']!r} is not in stages {stages}")
    return layout


def hop_dirs(layout) -> list:
    return [hop["dir"] for hop in layout["hops"]]


def stages_of_dir(layout, stage_dir) -> tuple:
    """(source-side stage, target-side stage) for one hop folder."""
    for hop in layout["hops"]:
        if hop["dir"] == stage_dir:
            return hop["from"], hop["to"]
    return layout["stages"][0], layout["stages"][-1]


def final_hop_dir(layout) -> str:
    """The folder holding the tables a run builds by default."""
    return layout["hops"][-1]["dir"]


def cloud_stage(layout) -> str:
    return (layout.get("cloud") or {}).get("stage", "cloud")


def table_prefixes(layout) -> list:
    return (layout.get("cloud") or {}).get("table_prefixes", [])
