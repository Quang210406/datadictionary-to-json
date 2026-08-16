"""Score the program's output against the hand-built dictionary.

The manual sheet is ground truth: a human read the files and wrote down what
they mean. This turns "does it work?" into a number per column, so a reviewer
can see exactly which parts are trustworthy and which are not.

Rows are matched on the DWH field plus its immediate source field, because
that pair is what identifies a mapping — including under n-1, where several
rows share one target.

    python src/compare.py real_data-4.xlsx output.json
"""

import json
import re
import sys
import unicodedata
from collections import Counter

import pandas as pd

from assemble import field_key, stages_in

# Each stage group occupies five columns in the manual sheet, in pipeline
# order. The stage list is read from the output being scored, so a manual
# sheet with a different number of groups is handled without configuration.
STAGE_WIDTH = 5


def stage_offsets(stages) -> dict:
    return {stage: i * STAGE_WIDTH for i, stage in enumerate(stages)}
FIELDS = ["table", "column", "path", "datatype", "size"]
HEADER_ROW = 2  # 0-based row holding "Tên Bảng", "Tên Cột", ...


def _clean(value):
    """Trim, and fold Unicode to one form.

    macOS stores filenames decomposed (NFD) while text typed into a cell is
    composed (NFC), so the same Vietnamese path compares unequal byte-wise
    unless both sides are normalised.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return unicodedata.normalize("NFC", str(value)).strip()


def read_manual(path, offsets) -> dict:
    df = pd.read_excel(path, header=None)
    rows = {}
    for i in range(HEADER_ROW + 1, len(df)):
        row = {}
        for stage, off in offsets.items():
            for k, name in enumerate(FIELDS):
                row[f"{stage}_{name}"] = _clean(df.iloc[i, off + k])
        row["description"] = _clean(df.iloc[i, 20])
        row["logic"] = _clean(df.iloc[i, 22])
        if not row["dwh_column"]:
            continue
        key = (field_key(row["dwh_table"], row["dwh_column"]),
               field_key(row["staging_table"], row["staging_column"]))
        rows.setdefault(key, row)
    return rows


def read_output(path) -> tuple:
    """Rows keyed for comparison, plus the stage list the output actually has."""
    records = json.loads(open(path, encoding="utf-8").read())
    offsets = stage_offsets(stages_in(records))
    rows = {}
    for record in records:
        by_stage = {e["stage"]: e for e in record["lineage"]}
        row = {}
        for stage in offsets:
            entry = by_stage.get(stage)
            for name in FIELDS:
                src = {"path": "offline_path"}.get(name, name)
                row[f"{stage}_{name}"] = _clean(entry.get(src)) if entry else ""
        row["description"] = _clean(record.get("description"))
        logic = ""
        for entry in record["lineage"]:
            for source in entry["sources"]:
                logic = _clean(source.get("transformation_logic")) or logic
        row["logic"] = logic
        key = (field_key(row["dwh_table"], row["dwh_column"]),
               field_key(row["staging_table"], row["staging_column"]))
        rows.setdefault(key, row)
    return rows, offsets


MAX_MISMATCHES = 40


def _score(manual, produced, columns, equal, excerpt=60) -> dict:
    """Match two dictionaries of rows and score them column by column.

    Both ground-truth formats reduce to the same problem: rows keyed by
    (target field, source field), compared per column under rules that differ
    by format. Only the columns and `equal` differ, so the matching, counting
    and reporting live here once.

    `equal(column, manual_value, program_value) -> bool` decides agreement.
    A column blank on both sides is skipped: that is agreement about absence,
    not a verified value.
    """
    matched = sorted(set(manual) & set(produced), key=str)
    only_manual = sorted(set(manual) - set(produced), key=str)
    agree, compared, mismatches = Counter(), Counter(), []

    for key in matched:
        for col in columns:
            a, b = manual[key].get(col, ""), produced[key].get(col, "")
            if not a and not b:
                continue
            compared[col] += 1
            if equal(col, a, b):
                agree[col] += 1
            elif len(mismatches) < MAX_MISMATCHES:
                mismatches.append({"row": f"{key[0]} <- {key[1]}", "column": col,
                                   "manual": a[:excerpt], "program": b[:excerpt]})

    total_c, total_a = sum(compared.values()), sum(agree.values())
    return {
        "manual_rows": len(manual), "program_rows": len(produced),
        "matched_rows": len(matched),
        "rows_only_in_manual": [f"{a} <- {b}" for a, b in only_manual][:10],
        "rows_only_in_program": len(set(produced) - set(manual)),
        "overall_field_accuracy": (f"{total_a}/{total_c} ({total_a / total_c:.1%})"
                                   if total_c else "n/a"),
        "by_column": {c: f"{agree[c]}/{compared[c]} ({agree[c] / compared[c]:.0%})"
                      for c in columns if compared[c]},
        "mismatches": mismatches,
    }


def compare(manual_path, output_path) -> dict:
    """Archive mode: four stage groups, plus description and logic."""
    produced, offsets = read_output(output_path)
    columns = ([f"{s}_{f}" for s in offsets for f in FIELDS]
               + ["description", "logic"])

    def equal(col, a, b):
        if a == b:
            return True
        # A path is a citation the human typed against the file the program
        # opened; prose is compared on its opening, not its full wording.
        if col.endswith("_path"):
            return a.split("/")[-1] == b.split("/")[-1]
        if col in ("description", "logic"):
            return a[:40] == b[:40]
        return False

    return _score(read_manual(manual_path, offsets), produced, columns, equal)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__); sys.exit(2)
    views = "--views" in sys.argv
    result = (compare_views if views else compare)(args[0], args[1])
    print(f"manual rows: {result['manual_rows']} | program rows: "
          f"{result['program_rows']} | matched: {result['matched_rows']}")
    print(f"\nOVERALL FIELD ACCURACY: {result['overall_field_accuracy']}\n")
    for col, score in result["by_column"].items():
        print(f"  {col:22} {score}")
    if result["rows_only_in_manual"]:
        print("\nIn your sheet but not produced:")
        for r in result["rows_only_in_manual"]:
            print(f"  - {r}")
    if result["mismatches"]:
        print(f"\nField mismatches ({len(result['mismatches'])} shown):")
        for m in result["mismatches"][:15]:
            print(f"  {m['row']}\n     {m['column']}: manual={m['manual']!r} "
                  f"program={m['program']!r}")
    json.dump(result, open("compare.json", "w"), indent=2, ensure_ascii=False)
    print("\nWrote compare.json")




# ------------------------------------------------- SQL view ground truth
#
# The manual SQL sheet is flat: one header row, one row per (view column,
# source field). Rows match on that pair, so n-1 columns line up correctly.
#
# Table and column names compare case-insensitively: the agent is told to copy
# verbatim, so it emits `address` where the SQL writes `address`, while a
# person writing the sheet by hand naturally types `ADDRESS`. Both are the
# same identifier and neither is wrong.

VIEW_HEADERS = {"source_schema": "Source Schema", "source_table": "Source Table",
                "source_column": "Source Column", "view_name": "View Name",
                "view_column": "View Column", "role": "Role",
                "transformation": "Transformation", "path": "Đường dẫn"}
VIEW_COMPARED = ["source_schema", "source_table", "source_column", "role",
                 "transformation", "path"]
CASELESS = {"source_schema", "source_table", "source_column", "role"}


def _squash(text):
    """An expression reduced to its tokens.

    Collapses runs of whitespace and drops spacing around brackets and commas,
    so `COALESCE( (SELECT x` and `COALESCE((SELECT x` compare equal. Nothing
    else is forgiven: different tokens, different order or different literals
    still count as a mismatch.
    """
    squashed = " ".join(text.split()).lower()
    return re.sub(r"\s*([(),])\s*", r"\1", squashed)


def _view_key(row):
    return (field_key(row["view_name"], row["view_column"]),
            field_key(row["source_table"], row["source_column"]))


def read_manual_views(path) -> dict:
    df = pd.read_excel(path)
    lookup = {}
    for field, header in VIEW_HEADERS.items():
        for col in df.columns:
            if _clean(col).lower().lstrip("s") == _clean(header).lower().lstrip("s"):
                lookup[field] = col
                break
    rows = {}
    for _, r in df.iterrows():
        row = {f: _clean(r[c]) if c in df.columns else "" for f, c in lookup.items()}
        if not row.get("view_column"):
            continue
        rows.setdefault(_view_key(row), row)
    return rows


def read_output_views(path) -> dict:
    records = json.loads(open(path, encoding="utf-8").read())
    rows = {}
    for record in records:
        by_stage = {e["stage"]: e for e in record["lineage"]}
        view = by_stage.get("view")
        if not view:
            continue
        source = (view.get("sources") or [{}])[0]
        row = {
            "source_schema": _clean(source.get("schema")),
            "source_table": _clean(source.get("table")),
            "source_column": _clean(source.get("column")),
            "view_name": _clean(view.get("table")),
            "view_column": _clean(view.get("column")),
            "role": _clean(source.get("role")),
            "transformation": _clean(source.get("transformation_logic")),
            "path": _clean(view.get("offline_path")),
        }
        rows.setdefault(_view_key(row), row)
    return rows


def compare_views(manual_path, output_path) -> dict:
    """SQL mode: identifiers compare case-insensitively, expressions by token."""
    def equal(col, a, b):
        if a == b:
            return True
        if col in CASELESS:
            return a.upper() == b.upper()
        if col == "path":
            return a.split("/")[-1] == b.split("/")[-1]
        if col == "transformation":
            return _squash(a) == _squash(b)
        return False

    return _score(read_manual_views(manual_path), read_output_views(output_path),
                  VIEW_COMPARED, equal, excerpt=70)


if __name__ == "__main__":
    main()
