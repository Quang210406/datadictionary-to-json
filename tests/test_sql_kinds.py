"""What a folder of .sql scripts does when they are not all the same statement.

    python tests/test_sql_kinds.py

No API key, no quota, no network. Only the ONE ai-shaped step is stubbed:
agent.convert is replaced with a perfect reader of the synthetic scripts this
file writes, and it COUNTS ITS CALLS — because half of what is under test here
is which files never reach it.

The bug this exists to keep closed: a CREATE TABLE ... AS SELECT sat in a
folder of CREATE VIEW scripts and sorted first alphabetically. It passed the
old checkpoint 1 (which only grepped for the word "select"), reached a paid
API call, was extracted under the view prompt, and came out labelled a view
end to end. Worse than the label: the completeness anchor is a view's declared
column list, so declared_object found nothing, expected_count was None, and
the completeness check — the one that catches a truncated reply — switched
itself off in silence and the file was pooled into every headline percentage.

Five scripts, chosen so each failure mode has its own file:

  V1  a real view, declared column list        -> view_sql,  stage "view"
  T1  a CTAS with a declared column list       -> table_sql, stage "table"
  T2  a CTAS over an inline view (SELECT *)    -> table_sql, no anchor
  C1  the only CREATE VIEW is inside a comment -> unrecognised, never read
  N1  a GRANT: contains "select", creates nothing -> unrecognised, never read
"""

import contextlib
import io
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import assemble
import kinds
import main
import store as store_mod
from extract import classify_sql, declared_object, expected_column_count
from validate import coverage_metrics, validate_sql_input

# --- the synthetic scripts -------------------------------------------------
#
# V1 copies the real archive's shape exactly: a "--" banner above the
# statement, and CREATE split from OR REPLACE across two lines. Both details
# are load-bearing. The banner is why classification must strip comments
# before anchoring, and the split line is why the modifier run must cross
# newlines.

V1 = '''--------------------------------------------------------
--  DDL for View DEMO_VIEW
--------------------------------------------------------
CREATE
OR REPLACE FORCE EDITIONABLE VIEW "DEMO_VIEW" ("PARTY_ID", "OPEN_DT") AS
SELECT a.PARTY_ID, a.OPEN_DT FROM RAW_PARTY a;
'''

T1 = '''--------------------------------------------------------
--  DDL for Table DEMO_TABLE
--------------------------------------------------------
CREATE TABLE "DEMO_TABLE" ("PARTY_ID", "OPEN_DT") AS
SELECT a.PARTY_ID, a.OPEN_DT FROM RAW_PARTY a;
'''

# No declared list, and the outer SELECT is a star — the shape of the real
# a.sql. There is no honest completeness anchor here: knowing what "*" expands
# to needs the definition of RAW_PARTY, which lives in another file, and the
# governing principle forbids showing the model two files at once.
T2 = '''CREATE TABLE DEMO_STAR AS
SELECT * FROM (SELECT PARTY_ID, OPEN_DT FROM RAW_PARTY) A;
'''

# The trap a naive re.search() falls into: this file's only CREATE VIEW is
# documentation. Classifying on it would read a file by its comments.
C1 = '''-- CREATE VIEW "NOT_A_VIEW" ("X") AS
/* the view below was replaced by a materialised copy:
   CREATE VIEW "ALSO_NOT" ("Y") AS  */
SELECT X FROM SOMETHING;
'''

# Contains the word "select" and creates nothing. This is precisely the file
# the old checkpoint 1 would have waved through to a paid API call.
N1 = '''GRANT SELECT ON RAW_PARTY TO REPORTING_ROLE;
'''

SCRIPTS = {"V1_view.sql": V1, "T1_table.sql": T1, "T2_star.sql": T2,
           "C1_comment.sql": C1, "N1_grant.sql": N1}


def build_folder(root, names):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for name in names:
        (root / name).write_text(SCRIPTS[name], encoding="utf-8")
    return root


# --- the only stub ---------------------------------------------------------

CONVERT_CALLS = []

SELECT_LIST = re.compile(r"SELECT\s+(.*?)\s+FROM\s+(\w+)", re.S | re.I)


def _fake_convert(text, schema, kind):
    """A perfect agent, and a call counter.

    Deliberately does NOT use extract.declared_object: the parser is under
    test, so a stub that leaned on it could agree with a broken one. It reads
    the SELECT list with its own regex, skipping a star list the way a real
    model reads through an inline view to the columns underneath.
    """
    CONVERT_CALLS.append((kind, text.splitlines()[0][:40]))

    target = re.search(r'(?:VIEW|TABLE)\s+("[^"]+"|\w+)', text, re.I)
    target = target.group(1).strip('"') if target else None
    declared = re.search(r'\(\s*("[^)]*")\s*\)\s*AS\s', text, re.S)
    declared = re.findall(r'"([^"]+)"', declared.group(1)) if declared else []

    columns, source_table = [], None
    for select_list, table in SELECT_LIST.findall(text):
        if select_list.strip() == "*":
            continue                       # read through to the inline view
        columns = [c.strip().split(".")[-1] for c in select_list.split(",")]
        source_table = table
        break

    out = []
    for i, column in enumerate(columns):
        out.append({
            "target_table": target,
            "target_column": declared[i] if i < len(declared) else column,
            "source_schema": None,
            "source_table": source_table,
            "source_column": column,
            "source_alias": "a",
            "source_role": "value",
            "transformation_logic": "direct",
        })
    return out


# --- running one folder ----------------------------------------------------

def run_folder(folder, tag):
    """The real CLI entry point, on a temp folder, writing into it."""
    out = Path(folder)
    args = main.parse_args([
        "--sql", str(folder),
        "--out", str(out / f"{tag}.json"),
        "--xlsx", str(out / f"{tag}.xlsx"),
        "--report", str(out / f"{tag}_report.json"),
        "--cache", str(out / f"{tag}_cache.json"),
    ])
    main.run(args)
    return (json.loads((out / f"{tag}.json").read_text(encoding="utf-8")),
            json.loads((out / f"{tag}_report.json").read_text(encoding="utf-8")))


def run_folder_quiet(folder, tag):
    with contextlib.redirect_stdout(io.StringIO()):
        return run_folder(folder, tag)


def stages_of(records):
    """{produced stage -> how many records carry it}."""
    counts = {}
    for record in records:
        stage = assemble.produced_entry(record)["stage"]
        counts[stage] = counts.get(stage, 0) + 1
    return counts


# --- a half-declared registry must not import ------------------------------

def registry_rejects(**overrides):
    """True if _check() refuses a registry holding this kind.

    Reaches into _REGISTRY on purpose. The module's whole claim is that a
    half-declared kind stops the program at import instead of degrading in the
    middle of a run, and the only way to show that is to declare one.
    """
    fields = dict(name="probe", schema_file="view_record.json",
                  reader=kinds.TEXT, header_anchors=None, statement="PROBE")
    fields.update(overrides)
    original = kinds._REGISTRY
    try:
        kinds._REGISTRY = original + (kinds.SourceKind(**fields),)
        kinds._check()
        return False
    except ValueError:
        return True
    finally:
        kinds._REGISTRY = original


def main_():
    store_mod.convert = _fake_convert          # the one stubbed thing
    tmp = Path(tempfile.mkdtemp(prefix="hecate_sqlkinds_"))
    failed = 0
    try:
        # --- classification, before anything is read ----------------------
        print(f"\n{'=' * 74}\nCLASSIFICATION (no file is read yet)\n{'=' * 74}")
        classified = {name: classify_sql(body) for name, body in SCRIPTS.items()}
        for name, kind in classified.items():
            anchor = expected_column_count(SCRIPTS[name])
            print(f"  {name:<16} -> {str(kind):<10} "
                  f"declared columns: {anchor if anchor else 'none'}")

        # --- the mixed folder, end to end ---------------------------------
        mixed = build_folder(tmp / "mixed", list(SCRIPTS))
        CONVERT_CALLS.clear()
        records, report = run_folder(mixed, "mixed")
        # Snapshot now: the views-only run below adds a call of its own, and
        # this count is the whole point of the stub.
        mixed_calls = list(CONVERT_CALLS)
        print(f"\n{'=' * 74}\nMIXED FOLDER\n{'=' * 74}")
        print(f"  files on disk        : {len(SCRIPTS)}")
        print(f"  read by the agent    : {len(mixed_calls)}")
        print(f"  file_kinds           : {report['file_kinds']}")
        print(f"  unrecognised_files   : {report['unrecognised_files']}")
        print(f"  records              : {len(records)}")
        print(f"  records per stage    : {stages_of(records)}")
        print(f"  stages_in(records)   : {assemble.stages_in(records)}")
        print(f"  complete_chains      : {report['coverage']['complete_chains']}")
        print(f"  coverage_by_stage    : "
              + ", ".join(f"{s}={c['complete_chains']}"
                          for s, c in report["coverage_by_stage"].items()))
        print("     Each record is judged against the stages ITS OWN file\n"
              "     declared, not against the union [source, table, view] —\n"
              "     which no record here was ever meant to have, and which\n"
              "     scored these same six records 0/6 before grouping.")

        print("\n  one record per produced stage:")
        seen = set()
        for record in records:
            entry = assemble.produced_entry(record)
            if entry["stage"] in seen:
                continue
            seen.add(entry["stage"])
            src = record["lineage"][0]
            print(f"    {entry['stage']:<6} {entry['table']}.{entry['column']:<10}"
                  f" from {src['table']}.{src['column']}")

        # --- a views-only folder must be untouched by any of this ---------
        views_only = build_folder(tmp / "viewsonly", ["V1_view.sql"])
        v_records, v_report = run_folder_quiet(views_only, "v")

        checks = [
            # classification
            ("a CREATE VIEW script classifies as view_sql",
             classified["V1_view.sql"] == "view_sql"),
            ("a CTAS with a declared list classifies as table_sql",
             classified["T1_table.sql"] == "table_sql"),
            ("a CTAS over an inline view classifies as table_sql",
             classified["T2_star.sql"] == "table_sql"),
            ("a CREATE VIEW inside a comment classifies as nothing",
             classified["C1_comment.sql"] is None),
            ("a GRANT containing the word 'select' classifies as nothing",
             classified["N1_grant.sql"] is None),

            # the money question
            ("an unrecognised script costs ZERO agent calls",
             len(mixed_calls) == 3
             and not any("GRANT" in t or "NOT_A_VIEW" in t
                         for _, t in mixed_calls)),
            ("checkpoint 1 rejects an unrecognised script outright",
             bool(validate_sql_input(SCRIPTS["N1_grant.sql"]))
             and bool(validate_sql_input(SCRIPTS["C1_comment.sql"]))),
            ("checkpoint 1 refuses a CTAS handed over as a view",
             bool(validate_sql_input(SCRIPTS["T1_table.sql"], "view_sql"))),
            ("...and accepts it as what it is",
             not validate_sql_input(SCRIPTS["T1_table.sql"], "table_sql")),

            # per-record stages: one dictionary, each record justified by its
            # own file
            ("a mixed folder produces ONE dictionary",
             len(records) == 6),
            ("view records carry stage 'view'",
             stages_of(records).get("view") == 2),
            ("CTAS records carry stage 'table'",
             stages_of(records).get("table") == 4),
            ("no record is labelled with a stage its own file did not state",
             set(stages_of(records)) == {"view", "table"}),
            ("the report names the statement each file was read as",
             report["file_kinds"] == {"V1_view.sql": "view_sql",
                                      "T1_table.sql": "table_sql",
                                      "T2_star.sql": "table_sql"}),
            ("the report names the files it refused",
             sorted(report["unrecognised_files"])
             == ["C1_comment.sql", "N1_grant.sql"]),

            # completeness is asked per produced stage, never against the union
            ("records complete for their own kind are NOT scored against the "
             "union of every kind in the folder",
             report["coverage"]["complete_chains"].startswith("6/6")),
            ("each produced stage is reported on its own stages",
             {s: c["complete_chains"] for s, c in
              report["coverage_by_stage"].items()}
             == {"view": "2/2 (100%)", "table": "4/4 (100%)"}),
            ("chain diagnostics agree with coverage",
             report["chain_diagnostics"]["complete_chains"] == 6),
            ("a record missing its source is still reported incomplete",
             coverage_metrics(
                 [{"description": None, "lineage": [
                     {"stage": "view", "table": "V", "column": "C",
                      "datatype": None, "sources": []}]}],
                 ["source", "view"], {"view": ["source", "view"]}
             )["complete_chains"].startswith("0/1")),

            # the completeness anchor, which is what silently switched off
            ("a declared column list is a checkable anchor, view or table",
             expected_column_count(V1) == 2 and expected_column_count(T1) == 2),
            ("a CTAS over SELECT * has no anchor to check against",
             expected_column_count(T2) is None),
            ("the generalised parser reads a table header, not just a view",
             declared_object(T1) == ("DEMO_TABLE", ["PARTY_ID", "OPEN_DT"])),

            # a views-only folder behaves exactly as it did before
            ("a views-only folder still yields stages [source, view]",
             assemble.stages_in(v_records) == ["source", "view"]),
            ("a views-only folder reports its chains complete",
             v_report["coverage"]["complete_chains"].startswith("2/2")),
            ("a views-only folder gets NO per-stage block, which would be a "
             "verbatim copy of coverage",
             "coverage_by_stage" not in v_report),

            # one entry in one file, or it does not import
            ("a TEXT kind with no statement is rejected at import",
             registry_rejects(statement=None)),
            ("an EXCEL kind with a statement is rejected at import",
             registry_rejects(reader=kinds.EXCEL,
                              header_anchors=(("a",), ("b",)))),
            ("a statement already claimed by another kind is rejected",
             registry_rejects(statement="VIEW")),
            ("a multi-word statement is rejected",
             registry_rejects(statement="MATERIALIZED VIEW")),
            ("the real registry still imports clean",
             kinds.get("table_sql").stage == "table"
             and kinds.get("view_sql").stage == "view"),
        ]

        print(f"\n{'=' * 74}\nASSERTIONS\n{'=' * 74}")
        for label, ok in checks:
            print(f"  {'PASS' if ok else 'FAIL'}  {label}")
            failed += not ok
        print(f"\n  {len(checks) - failed}/{len(checks)} passed")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main_())
