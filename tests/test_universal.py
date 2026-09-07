"""A dictionary and a chain from prose alone, and from all three formats at once.

    python tests/test_universal.py

No API key, no quota, no network. Only the ONE ai-shaped step is stubbed:
agent.convert is replaced by a perfect reader of the synthetic documents this
file writes, and it COUNTS ITS CALLS — because half of what is under test is how
many calls a large document costs and which files never reach one at all.

The bug this exists to close: point the program at a folder of PDFs and the
dictionary came back EMPTY. Three of five kinds produced lineage; the one that
read documents produced descriptions only and never reached assemble.py. So a
document could add meaning to a field Excel or SQL had already found, and could
not discover a field or contribute a chain.

The fixture is built so the answer is known by construction, and so that the
interesting property is not testable any other way:

    doc_a  says  DWH_ORDER  <- STG_ORDER
    doc_b  says  STG_ORDER  <- SRC_ORDER

NEITHER DOCUMENT STATES THE PIPELINE. The order SRC -> STG -> DWH exists only
in the join of the two, which is the whole claim of the rewrite: the chain
emerges from the records rather than from a declared layout. A wrong stage order
passes fidelity and passes completeness, so this is also the only place that
particular error can be caught.

What it does NOT prove, and the report should say so: nothing here shows a model
reading a real Vietnamese design document correctly. The extraction is stubbed.
This tests the plumbing, the join and the derivation — not the reading.
"""

import contextlib
import io
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import agent
import assemble
import kinds
import main
import mapping
import order
import readers
import sections
import store as store_mod

PASS = FAIL = 0
CALLS = []
READS = []


def check(label, got, want=True):
    global PASS, FAIL
    ok = got == want
    if ok:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}\n          got {got!r}, want {want!r}")


# --- the synthetic corpus --------------------------------------------------

ROW = re.compile(r"^\s*\|(.+)\|\s*$")


def _table(target, source, columns, rows=6):
    lines = [f"## Bảng {target}", "",
             "| Target Table | Target Column | Source Table | Source Column | Rule |",
             "|---|---|---|---|---|"]
    for i in range(rows):
        col = columns[i % len(columns)] + (f"_{i}" if i >= len(columns) else "")
        lines.append(f"| {target} | {col} | {source} | SRC_{col} | direct |")
    return "\n".join(lines) + "\n"


DOC_A = ("# Thiết kế kho dữ liệu\n\nTài liệu mô tả tầng kho.\n\n"
         + _table("DWH_ORDER", "STG_ORDER", ["ORDER_ID", "AMOUNT", "STATUS"]))
DOC_B = ("# Thiết kế tầng staging\n\nTài liệu mô tả tầng staging.\n\n"
         + _table("STG_ORDER", "SRC_ORDER", ["SRC_ORDER_ID", "SRC_AMOUNT"]))


def fake_convert(text, schema, source_kind):
    """A perfect reader of the tables above — and a call counter."""
    CALLS.append(source_kind)
    if source_kind != "doc_lineage":
        return []
    out = []
    for line in text.splitlines():
        match = ROW.match(line)
        if not match:
            continue
        cells = [c.strip() for c in match.group(1).split("|")]
        if len(cells) < 5 or cells[0] in ("Target Table", "") or set(cells[0]) <= set("-: "):
            continue
        out.append({"target_table": cells[0], "target_column": cells[1],
                    "source_table": cells[2], "source_column": cells[3],
                    "transformation_logic": cells[4], "section": None})
    return out


def run_docs(folder, extra=()):
    args = main.parse_args(["--docs", str(folder), *extra])
    main.apply_mode_defaults(args)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        main.run(args)
    return buffer.getvalue(), args


def main_test():
    agent.convert = fake_convert
    store_mod.convert = fake_convert

    real_read = readers.read
    def counting_read(path):
        READS.append(str(path))
        return real_read(path)
    readers.read = counting_read
    store_mod.readers.read = counting_read

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        docs = tmp / "docs"
        docs.mkdir()
        (docs / "doc_a.md").write_text(DOC_A, encoding="utf-8")
        (docs / "doc_b.md").write_text(DOC_B, encoding="utf-8")
        out = tmp / "out"

        print("\nA FOLDER OF DOCUMENTS PRODUCES A DICTIONARY")
        CALLS.clear(); READS.clear()
        text, args = run_docs(docs, [
            "--out", str(out / "docs.json"), "--xlsx", str(out / "docs.xlsx"),
            "--report", str(out / "docs_report.json"),
            "--cache", str(tmp / "cache.json")])
        import json
        records = json.loads(Path(args.out).read_text(encoding="utf-8"))
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))

        check("the dictionary is not empty", len(records) > 0)
        check("every record carries a chain",
              all(len(r["lineage"]) >= 2 for r in records))
        check("both documents were read", len(report["documents"]), 2)
        check("claims were extracted", report["claims"] > 0)

        print("\nTHE CHAIN EMERGES FROM JOINING TWO DOCUMENTS")
        stages = report["chain_diagnostics"]["stages"]
        check("three stages were derived, though neither document states one",
              len(stages), 3)
        deep = [r for r in records if len(r["lineage"]) == 3]
        check("at least one chain spans all three", len(deep) > 0)
        if deep:
            chain = [e["table"] for e in deep[0]["lineage"]]
            check("and it runs SRC -> STG -> DWH",
                  chain, ["SRC_ORDER", "STG_ORDER", "DWH_ORDER"])

        print("\nA PROSE SUBJECT IS MARKED AS RESTING ON TEXT")
        check("every doc claim is flagged subject_from_text",
              report["subject_from_text"], report["claims"])

        print("\nEVIDENCE IS THE SECTION, NOT JUST THE FILE")
        links = {e.get("doc_link") for r in records for e in r["lineage"]
                 if e.get("doc_link")}
        check("doc_link carries a section id", len(links) > 0)

        print("\nCOMPLETENESS IS HONEST ABOUT PROSE")
        check("no document claims a completeness anchor",
              report["completeness"]["sources_checked"], 0)
        check("and each unchecked source says why",
              all(s["reason"] for s in report["completeness"]["not_checked"]))

        print("\nONE CONVERSION PER FILE, ONE CALL PER SECTION")
        check("each document was read exactly once", sorted(set(READS)) == sorted(READS))
        check("two files were read", len(READS), 2)
        check("more calls than files (sections, not documents)",
              len(CALLS) >= len(READS))

    print("\nA LARGE DOCUMENT IS SPLIT, AND NEVER MID-TABLE")
    big = "# Tài liệu lớn\n\n" + "".join(
        _table(f"DWH_T{i}", f"STG_T{i}", ["A", "B", "C"], rows=200)
        for i in range(6))
    parts = sections.split(big)
    check("it splits into several sections", len(parts) > 1)
    check("no section exceeds the cap",
          max(len(t) for _, t in parts) <= sections.MAX_CHARS)
    check("every table slice keeps a header row",
          all("Target Column" in t for _, t in parts if t.count("|") > 20))
    check("section ids are unique", len({i for i, _ in parts}), len(parts))
    check("section ids carry no cache-key separator",
          all("|" not in i for i, _ in parts))
    check("splitting is stable across runs",
          [i for i, _ in sections.split(big)], [i for i, _ in parts])

    print("\nA CYCLE IS REPORTED, NEVER RESOLVED")
    def claim(subject, src, path="x.md", ordinal=0):
        return mapping.Claim(
            subject_table=subject, subject_trusted=True, target_column="ID",
            source_schema=None, source_table=src, source_column="ID",
            source_alias=None, source_role="value", transformation_type=None,
            transformation_logic=None, target_datatype=None, target_size=None,
            source_datatype=None, source_size=None, evidence_path=path,
            evidence_section=None, kind="hop_spec", ordinal=ordinal)
    looped = order.derive([claim("A", "B"), claim("B", "C"), claim("C", "A")])
    check("the cycle is recorded", len(looped.back_edges) > 0)
    check("and the derivation still terminates", looped.count > 0)

    print("\nTHE POOL KEEPS TWO TABLES' COLUMNS APART")
    index = mapping.index_by_produced(
        [claim("ORDERS", "SRC"), claim("CUSTOMERS", "SRC")], assemble.field_key)
    check("a shared column name does not collide", len(index), 2)

    print("\nCLAIMS ARE ORDERED DETERMINISTICALLY")
    # Distinct evidence, because that is what real claims have: the ordinal is
    # an enumerate index within one file, so two claims can only tie if they
    # came from the same file at the same row, which cannot happen. What has to
    # hold is that pooling claims from SEVERAL files gives one answer no matter
    # what order the directory happened to yield them in — "first match" used
    # to mean within-file row order and silently becomes iteration order once
    # the pool is global.
    pool = [claim("A", "B", "b.xlsx", 1), claim("C", "D", "a.xlsx", 0),
            claim("E", "F", "a.xlsx", 1)]
    check("ordering does not depend on input order",
          [c.subject_table for c in mapping.ordered(pool)],
          [c.subject_table for c in mapping.ordered(list(reversed(pool)))])
    check("and it sorts by evidence, then by position in that evidence",
          [c.subject_table for c in mapping.ordered(pool)], ["C", "E", "A"])

    print("\nEVERY REGISTERED LINEAGE KIND HAS A NORMALISER")
    check("doc_lineage is live", "doc_lineage" in mapping.LINEAGE_KINDS)
    check("cloud_sheet states no mapping claim",
          "cloud_sheet" not in mapping.LINEAGE_KINDS)
    check("every lineage kind is registered in kinds.py",
          all(k in kinds.KINDS for k in mapping.LINEAGE_KINDS))

    print(f"\n  {PASS}/{PASS + FAIL} passed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main_test())
