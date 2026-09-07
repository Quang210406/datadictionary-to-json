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

    # Column-header captions, per source kind. Absent here on purpose: the
    # defaults live in kinds.py and cover this archive. An archive whose sheets
    # say "Destination Column" / "Origin Table" declares its own, e.g.
    #
    #   "header_anchors": {
    #     "hop_spec": [["target", "destination"], ["source", "origin"]]
    #   }
    #
    # Each inner list is the alternatives for one side; the two sides must
    # match DIFFERENT cells of the same row. This was the last archive-specific
    # fact still living in code while every other one had moved here — and the
    # one whose failure mode is worst, because unrecognised captions do not
    # fail: they switch the completeness check off, which is the check that
    # catches a truncated reply.
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

    # The same rules kinds._check applies to the built-in anchors, applied to
    # declared ones. Every one of these failures is silent: a capitalised
    # anchor never matches because header cells are lower-cased first, and an
    # empty group can never claim a cell — both end as "no header row found",
    # which reads as a sheet with no data rather than as a bad config.
    for kind, groups in (layout.get("header_anchors") or {}).items():
        if not groups or not all(groups):
            raise LayoutError(
                f"header_anchors for {kind!r} has an empty group; it could "
                "never match a cell, so no header row would ever be found and "
                "the completeness check would silently stop running.")
        for group in groups:
            for word in group:
                if not isinstance(word, str) or word != word.lower():
                    raise LayoutError(
                        f"header_anchors for {kind!r} contains {word!r}; "
                        "header cells are lower-cased before matching, so "
                        "anything not lower-case can never match.")
    return layout


def header_anchors(layout) -> dict:
    """{kind -> anchors} this archive declares, as the tuples kinds.py uses."""
    declared = (layout or {}).get("header_anchors") or {}
    return {kind: tuple(tuple(group) for group in groups)
            for kind, groups in declared.items()}


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
