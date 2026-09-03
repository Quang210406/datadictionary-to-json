"""Surveying a folder nobody has written a layout for.

    python tests/test_survey.py

No API key, no quota, no network, nothing stubbed. The survey reads directory
entries and workbook sheet NAMES; it never opens a cell, which is what makes it
safe to point at a folder nobody understands yet.

The line this holds is between two different kinds of claim:

  * what is IN the folder — checkable by anyone who opens it
  * what SHAPE the folder is — a guess

A wrong stage ORDER is the dangerous one. It passes fidelity (every value
still appears verbatim in its source file) and passes completeness (every row
still produced a record) and emits a confidently wrong pipeline. No single
file can verify it, so it would be the first claim in this system that nothing
can check. Hence: propose, show the evidence, and never apply.

Three folders:

  A  two hops named <FROM>_<TO>, the shape the convention describes
  B  the same folders renamed so the convention says nothing — the survey must
     still report contents, still propose, and say plainly that the order is
     the part it could not derive
  C  hop folders whose names chain only under ONE reading of where to split,
     so the split is derived rather than assumed
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from openpyxl import Workbook

import survey
from layout import validate_layout


def _book(path, sheet):
    """A workbook with a named sheet and nothing worth reading inside."""
    wb = Workbook()
    wb.active.title = sheet
    wb.active["A1"] = "not read by the survey"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def build(root, hops, cloud_name=None):
    """hops: [(folder, [table names])]"""
    root = Path(root)
    for folder, tables in hops:
        for table in tables:
            _book(root / folder / f"{table}.xlsx", table)
    if cloud_name:
        _book(root / cloud_name, "SOME_TABLE")
    return root


def main_():
    tmp = Path(tempfile.mkdtemp(prefix="hecate_survey_"))
    failed = 0
    try:
        a = build(tmp / "A", [
            ("SRC_STG", ["STG_PARTY", "STG_ACCOUNT"]),
            ("STG_DWH", ["DWH_PARTY", "DWH_ACCOUNT"]),
        ], cloud_name="Mapping_to_CLOUD.xlsx")

        b = build(tmp / "B", [
            ("inbound", ["STG_PARTY"]),
            ("curated", ["DWH_PARTY"]),
        ])

        # Only one split point makes these chain: RAW | STG_ZONE and
        # STG_ZONE | DWH. Splitting "RAW_STG_ZONE" as (RAW_STG, ZONE) leaves
        # nothing to join to.
        c = build(tmp / "C", [
            ("RAW_STG_ZONE", ["STG_X"]),
            ("STG_ZONE_DWH", ["DWH_X"]),
        ])

        facts_a = survey.survey(a)
        prop_a = survey.propose(facts_a)
        facts_b = survey.survey(b)
        prop_b = survey.propose(facts_b)
        facts_c = survey.survey(c)
        prop_c = survey.propose(facts_c)

        print("=" * 74)
        print("CASE A — folders follow the <FROM>_<TO> convention")
        print("=" * 74)
        print(survey.render(facts_a, prop_a))

        print()
        print("=" * 74)
        print("CASE B — folder names say nothing about order")
        print("=" * 74)
        for line in prop_b["warnings"]:
            print(f"  ! {line}")
        print(f"  facts still reported: "
              f"{[f['dir'] + '/' + str(f['workbooks']) for f in facts_b['folders']]}")

        print()
        print("=" * 74)
        print("CASE C — the split point is derived, not assumed")
        print("=" * 74)
        print(f"  stages: {prop_c['layout']['stages']}")
        for hop in prop_c["layout"]["hops"]:
            print(f"    {hop}")

        # nothing may have been written anywhere
        strays = [p for p in Path(tmp).rglob("*.json")]

        checks = [
            # facts
            ("every folder and its workbook count is reported",
             {f["dir"]: f["workbooks"] for f in facts_a["folders"]}
             == {"SRC_STG": 2, "STG_DWH": 2}),
            ("the table each workbook describes is reported",
             sorted(facts_a["folders"][0]["tables"])
             == ["STG_ACCOUNT", "STG_PARTY"]),
            ("table-name prefixes are counted",
             facts_a["table_prefixes"] == {"STG_": 2, "DWH_": 2}),
            ("a final-stage workbook is spotted by name",
             [c["file"] for c in facts_a["cloud_candidates"]]
             == ["Mapping_to_CLOUD.xlsx"]),

            # the proposal, where the convention holds
            ("the hop order is derived from the folder names",
             prop_a["layout"]["stages"][:3] == ["source", "staging", "dwh"]),
            ("each hop names the two stages it maps between",
             prop_a["layout"]["hops"]
             == [{"dir": "SRC_STG", "from": "source", "to": "staging"},
                 {"dir": "STG_DWH", "from": "staging", "to": "dwh"}]),
            ("a cloud stage is proposed when a candidate file exists",
             prop_a["layout"].get("cloud", {}).get("stage") == "cloud"),
            ("the proposal validates as a real layout",
             prop_a["valid"] and validate_layout(prop_a["layout"])),
            ("every guess carries its evidence",
             len(prop_a["evidence"]) >= 3
             and any("chain" in e for e in prop_a["evidence"])),
            ("prefix corroboration is reported for each hop",
             any("STG_*" in e for e in prop_a["evidence"])
             and any("DWH_*" in e for e in prop_a["evidence"])),

            # the proposal, where it does NOT
            ("a folder whose names carry no convention still reports contents",
             len(facts_b["folders"]) == 2
             and all(f["workbooks"] == 1 for f in facts_b["folders"])),
            ("...and still proposes a USABLE pipeline rather than giving up",
             bool(prop_b["layout"]["hops"]) and prop_b["valid"]
             and prop_b["layout"]["stages"][0] == "source"),
            ("...and says plainly that the ORDER is the unverifiable part",
             any("ORDER" in w for w in prop_b["warnings"])),

            # the split is derived
            ("the split point is chosen so the hops chain, not by position",
             prop_c["layout"]["hops"]
             == [{"dir": "RAW_STG_ZONE", "from": "source", "to": "stg_zone"},
                 {"dir": "STG_ZONE_DWH", "from": "stg_zone", "to": "dwh"}]),

            # the line that must not be crossed
            ("a proposal is never written anywhere on its own",
             strays == []),
            # Not asserted by assertion: every workbook above has a sentinel
            # in A1, and the survey's whole output is searched for it. If a
            # future change starts reading cells this fails rather than
            # quietly turning a free, safe operation into an expensive one.
            ("the survey reads no cell contents",
             "not read by the survey" not in json.dumps(
                 [facts_a, facts_b, facts_c, prop_a, prop_b, prop_c],
                 ensure_ascii=False))
        ]

        print()
        print("=" * 74)
        print("ASSERTIONS")
        print("=" * 74)
        for label, ok in checks:
            print(f"  {'PASS' if ok else 'FAIL'}  {label}")
            failed += not ok
        print(f"\n  {len(checks) - failed}/{len(checks)} passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main_())
