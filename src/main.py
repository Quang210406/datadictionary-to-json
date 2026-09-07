import argparse, json, sys
from collections import Counter
from pathlib import Path

import assemble
import emit
import entities
import kinds
import mapping
import order
from catalog import build_catalog, cloud_sheets, find_cloud_workbook
import readers
from extract import classify_sql, read_sql_text
from layout import (LayoutError, cloud_stage, final_hop_dir, header_anchors,
                    load_layout, table_prefixes)
from store import RecordStore
import descriptions
import rules_doc
import survey
import templates
from validate import (chain_diagnostics, completeness_report,
                      coverage_metrics, validate_assembled)

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schemas"


# Which schema file belongs to which source kind is declared once, in
# kinds.py, beside everything else about that kind. SCHEMA_DIR stays a module
# global read at call time, because the app corrects it after import: a frozen
# bundle does not preserve the path main.py computes from its own __file__.
def load_schemas():
    """The extraction contract per source kind, generated from the models.

    src/templates.py is the declaration; schemas/*.json are the same thing
    written out for anyone who wants to read the contract without reading
    Python. Generating rather than loading means the two cannot drift — and
    tests/test_templates.py asserts they serialise identically, so the file on
    disk stays an honest copy rather than a second source of truth.
    """
    return {kind: templates.json_schema(filename)
            for kind, filename in kinds.schema_files().items()}


def load_lineage_schema():
    """The assembled-output schema, checked against src/entities.py first.

    Read at call time for the same reason load_schemas() is: the app corrects
    SCHEMA_DIR after import, because a frozen bundle does not preserve the
    path main.py computes from its own __file__.
    """
    schema = json.loads((SCHEMA_DIR / "lineage.json").read_text(encoding="utf-8"))
    entities.reconcile_with_schema(schema)
    return schema


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python src/main.py",
        description="Assemble a data dictionary from an archive of hop specs.")
    parser.add_argument("--sql", metavar="DIR_OR_FILE",
                        help="folder of CREATE VIEW / CREATE TABLE .sql scripts "
                             "(or one file). Builds SQL lineage instead of an "
                             "archive chain. Each script is classified by the "
                             "statement it opens with; anything else is "
                             "reported and skipped.")
    parser.add_argument("--archive", metavar="DIR",
                        help="archive root: the hop folders and the final-stage "
                             "workbook, as described by the layout.")
    parser.add_argument("--layout", metavar="FILE",
                        help="JSON describing the archive's folders and stages. "
                             "Defaults to archive.json inside the archive, then "
                             "to the built-in layout.")
    parser.add_argument("--table", action="append", default=[], metavar="TABLE",
                        help="target table to build, e.g. DWH_TEMP_PARTY. "
                             "Repeatable; omit to build every DWH table found.")
    # These four default to None and are filled in by apply_mode_defaults()
    # once the mode is known. They used to default to the ARCHIVE's names in
    # both modes, which made every SQL run override all four or quietly write
    # into the archive's artefacts. Forgetting --report put lineage records in
    # a file named report; forgetting --cache mixed one mode's extractions
    # into the other's cache, at the price of an API call. Neither failed, and
    # neither looked wrong until someone opened the file.
    parser.add_argument("--survey", metavar="DIR",
                        help="report what is in an archive folder, and propose "
                             "a layout for it. Reads folder and sheet NAMES "
                             "only — no cell contents, no API call. The "
                             "proposal is printed for a person to accept; it "
                             "is never applied.")
    parser.add_argument("--survey-out", metavar="FILE",
                        help="write the proposed layout to FILE. Review it, "
                             "then pass it with --layout.")
    parser.add_argument("--rules-doc", metavar="FILE",
                        help="write an .xlsx saying, per entity attribute and "
                             "per document format, where in the document the "
                             "value is found. Needs no archive and no API "
                             "call; it describes the formats, not a run.")
    parser.add_argument("--from-docs", metavar="DIR_OR_FILE",
                        help="read prose documents (PDF, Word) for what they "
                             "say a field MEANS, and pre-fill the description "
                             "template with it. Each document is read on its "
                             "own; matching the meanings to real fields is done "
                             "afterwards, in Python.")
    parser.add_argument("--describe-template", metavar="FILE",
                        help="write an .xlsx with one row per distinct target "
                             "field and an empty description column, for a "
                             "person to fill in. Costs no API call.")
    parser.add_argument("--descriptions", metavar="FILE",
                        help="a filled-in template. Its text is joined into "
                             "the spreadsheet and counted in the report; it is "
                             "never written into the JSON dictionary, which "
                             "means only what the source documents state.")
    parser.add_argument("--docs", metavar="DIR_OR_FILE",
                        help="build a dictionary from prose documents (PDF, "
                             "Word) alone: read each for the MAPPINGS it "
                             "states, not just field meanings. Each document is "
                             "split into sections and each section is read on "
                             "its own; the chain is joined afterwards, in "
                             "Python, exactly as for the other two modes.")
    parser.add_argument("--assembler", default="legacy",
                        choices=["legacy", "unified", "both"],
                        help="which assembler builds the chain. 'legacy' is the "
                             "per-mode resolver the published numbers were "
                             "measured with; 'unified' is the one claim pool "
                             "shared by every format; 'both' runs each and "
                             "reports the difference, which is how the two were "
                             "shown to agree record-for-record.")
    parser.add_argument("--generate-template", nargs="+", metavar="DOC",
                        help="induce a Pydantic extraction contract from one or "
                             "more example documents and write it, as readable "
                             "Python, under out/generated/. Needs docling-graph. "
                             "The module is written only if its own "
                             "verification passes, and it is never adopted "
                             "automatically — a generated contract is embedded "
                             "in the prompt, so a person reads it before it "
                             "decides what a dictionary means.")
    parser.add_argument("--out", default=None,
                        help="lineage RECORDS as JSON "
                             "(default: views.json / output.json by mode).")
    parser.add_argument("--xlsx", default=None,
                        help="same dictionary in the hand-built layout "
                             "(default: views.xlsx / output.xlsx by mode).")
    parser.add_argument("--report", default=None,
                        help="coverage and per-file METRICS as JSON "
                             "(default: views_report.json / report.json).")
    parser.add_argument("--cache", default=None,
                        help="extraction cache; delete it to force re-reading "
                             "(default: .cache/views.json / .cache/records.json). "
                             "Each mode has its own: sharing one costs an API "
                             "call and files a script under the wrong run.")
    return parser.parse_args(argv)


# What each mode writes when it is not told otherwise. Named per mode so that
# running either one with no output flags at all is correct and cannot touch
# the other's files — the flags are for overriding, not for basic safety.
# Written into out/ rather than the project root. A run produces four files
# and there are two modes, so the root accumulated eight generated artefacts
# sitting beside the source — which makes a repo look like a working directory
# and makes it easy to lose track of which are inputs. out/ is already
# gitignored.
OUT_DIR = "out"

MODE_DEFAULTS = {
    "sql":     {"out": f"{OUT_DIR}/views.json",  "xlsx": f"{OUT_DIR}/views.xlsx",
                "report": f"{OUT_DIR}/views_report.json",
                "cache": ".cache/views.json"},
    "archive": {"out": f"{OUT_DIR}/output.json", "xlsx": f"{OUT_DIR}/output.xlsx",
                "report": f"{OUT_DIR}/report.json",
                "cache": ".cache/records.json"},
    # Its own four, like the other two. A docs run that wrote output.json would
    # silently replace an archive dictionary with a prose-derived one, and the
    # two are not the same claim about the world.
    "docs":    {"out": f"{OUT_DIR}/docs.json", "xlsx": f"{OUT_DIR}/docs.xlsx",
                "report": f"{OUT_DIR}/docs_report.json",
                "cache": ".cache/docs.json"},
}


def mode_of(args) -> str:
    """Which of the three modes this run is.

    Read with getattr so a namespace built by hand still works — the desktop
    app assembles one and sets its four output paths itself.
    """
    if getattr(args, "sql", None):
        return "sql"
    if getattr(args, "docs", None):
        return "docs"
    return "archive"


def apply_mode_defaults(args):
    """Fill in whichever output paths the caller left unset, per mode.

    Uses getattr/setattr rather than reading attributes directly so it also
    works on a namespace built by hand — the desktop app assembles one and
    sets all four itself, and anything it has already set is left alone.
    """
    for field, value in MODE_DEFAULTS[mode_of(args)].items():
        if getattr(args, field, None) is None:
            setattr(args, field, value)
    return args


def check_output_paths(args):
    """Refuse to write two different things to one path.

    --out and --report hold different documents (records vs metrics), so
    naming them the same file means one silently destroys the other. This is
    the mistake the old shared defaults invited, and it is worth catching even
    now that it has to be typed on purpose.
    """
    named = {"--out": args.out, "--report": args.report, "--xlsx": args.xlsx}
    for a, b in (("--out", "--report"), ("--out", "--xlsx"),
                 ("--report", "--xlsx")):
        if Path(named[a]).resolve() == Path(named[b]).resolve():
            print(f"{a} and {b} both point at {named[a]}; they hold different "
                  "documents and one would overwrite the other.")
            sys.exit(1)


def print_block(title, mapping):
    print(f"\n{title}")
    for name, value in mapping.items():
        print(f"  {name}: {value}")


def _doc_store(args):
    """A store for reading prose documents.

    Its own cache file: document extractions are keyed by content like every
    other, but mixing them into the archive's cache would put a 138-page PDF
    beside the hop specs and make either one harder to ship on its own.
    """
    cache = Path(args.cache).parent / "documents.json"
    return RecordStore(load_schemas(), cache_path=str(cache))


def load_overlay(args, stages):
    """The description overlay, if this run was given one."""
    path = getattr(args, "descriptions", None)
    return descriptions.load(path, stages) if path else None


def finish(records, report, args, emitter, extra_blocks=(), overlay=None):
    """Report, print and write — identical for every mode.

    Only the spreadsheet layout and the mode-specific block of numbers differ,
    so both arrive as arguments rather than as a second copy of this code.
    """
    # Which sources completeness could actually be checked on. Computed here
    # so both modes get it from one place, and printed only when something was
    # NOT checked — a run where every source had an anchor has nothing to say.
    report["completeness"] = completeness_report(report["sources"])
    report["assembled_shape"] = validate_assembled(records, load_lineage_schema())

    # The stage list this run's field keys were computed under. Taken from the
    # chain diagnostics because in archive mode that is the LAYOUT's list,
    # which is stable no matter which tables were built — unlike the stages
    # actually present in the records, which shrink when a table has no cloud
    # copy and would make a valid description file look like it belonged to a
    # different archive.
    stages = (report.get("chain_diagnostics") or {}).get("stages") or []

    if overlay is not None:
        report["descriptions"] = descriptions.merge_report(records, overlay)
    prefill = None
    if getattr(args, "from_docs", None):
        root = Path(args.from_docs)
        docs = ([p for p in sorted(root.rglob("*"))
                 if p.is_file() and readers.for_path(p)
                 and p.suffix.lower() not in (".sql", ".txt")]
                if root.is_dir() else [root])
        if not docs:
            print(f"\nNo readable documents under {args.from_docs}. "
                  f"This build reads: {sorted(readers.readable_extensions())}")
        else:
            print(f"\nReading {len(docs)} document(s) for field meanings...")
            prefill, doc_report = descriptions.from_documents(
                records, _doc_store(args), docs)
            report["from_documents"] = doc_report
            for entry in doc_report["documents_read"]:
                print(f"  {entry['file'][:56]}: "
                      f"{entry['definitions']} definition(s)")
            print(f"  matched to a field in this dictionary: "
                  f"{doc_report['definitions_matched']}")
            if doc_report["definitions_unmatched"]:
                print(f"  described a field this run did not build: "
                      f"{doc_report['definitions_unmatched']} "
                      "(reported, not an error)")
                for ex in doc_report["unmatched_examples"]:
                    print(f"    - {ex}")

    if getattr(args, "describe_template", None):
        path, count = descriptions.export_template(
            records, args.describe_template, stages, prefill)
        filled = len(prefill or {})
        print(f"\nDescription template: {count} distinct target field(s) "
              f"-> {path}")
        if filled:
            print(f"  {filled} pre-filled from documents; the rest are for a "
                  "person. Every pre-filled row names its source.")
    print_block("Coverage (what a reviewer should look at):", report["coverage"])
    for title, mapping in extra_blocks:
        print_block(title, mapping)

    unchecked = report["completeness"]["not_checked"]
    if unchecked:
        print(f"\nCompleteness NOT CHECKED on {len(unchecked)} source(s) — "
              f"{report['completeness']['sources_checked']} checked:")
        for item in unchecked:
            print(f"  - {item['source']} ({item['kind']}): {item['reason']}")
            print(f"      {item['records_emitted']} record(s) emitted, "
                  "against no stated expectation")

    print(f"\nFiles read: {report['files_read']} "
          f"({report['files_converted']} converted, rest cached)")
    joined = report.get("descriptions")
    if joined:
        print(f"\nDescriptions joined from {Path(joined['source']).name}: "
              f"{joined['matched']}/{joined['fields']} field(s) described")
        # Orphans are named, never dropped. A renamed table orphans every one
        # of its descriptions at once, and somebody's work is recoverable by
        # hand only while it is still visible.
        if joined["orphaned"]:
            print(f"  ORPHANED — {joined['orphaned']} description(s) match no "
                  "field in this run (kept in the file, not discarded):")
            for key in joined["orphaned_keys"][:10]:
                print(f"    - {key}")
        if joined["undescribed"]:
            print(f"  {joined['undescribed']} field(s) still have no "
                  "description from either a document or a person")

    shape = report["assembled_shape"]
    if shape["violations"]:
        print(f"\nASSEMBLED SHAPE: {shape['violations']} violation(s) against "
              f"{shape['schema']} — {shape['clean_records']}/"
              f"{shape['records_checked']} records clean")
        for example in shape["examples"]:
            print(f"  - {example}")

    errors = report.get("source_errors", [])
    if errors:
        print(f"Extraction problems: {len(errors)}")
        for error in errors[:10]:
            print(f"  - {error}")

    # Create the output folders before writing. This runs after every file has
    # been read, so a missing directory here throws away work that may have
    # cost API calls — the most expensive possible moment to discover a typo.
    for target in (args.report, args.out, args.xlsx):
        Path(target).parent.mkdir(parents=True, exist_ok=True)

    Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
    Path(args.out).write_text(json.dumps(records, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    emitter(records, args.xlsx)
    print(f"\nWrote {len(records)} records -> {args.out}, {args.xlsx}, {args.report}")


# ------------------------------------------------------------- claim pools
#
# One pool per mode, because discovering WHICH files to read differs per corpus
# even though what is done with them afterwards no longer does.


def archive_claims(catalog, store, targets):
    """Claims for the tables reachable from `targets`, loading LAZILY.

    Reachability, not the whole catalog. `resolve_table` visits files as it
    discovers them, so a run touches only the tables it actually reaches — 20
    workbooks of 89 for the two published targets. Building the pool eagerly
    would convert all 89 and cost 69 needless API calls on a free-tier key, so
    this reproduces the same walk and collects claims as it goes.

    The catalog survives, demoted to what its own docstring always claimed it
    was: an index saying which FILE defines which table. What it no longer does
    is repair the join key — mapping.claims_from stamps the sheet name as the
    subject before anything is pooled.
    """
    seen, queue, claims, pairs = set(), list(targets), [], []
    while queue:
        table = queue.pop(0)
        key = assemble.table_key(table)
        if key is None or key in seen:
            continue
        seen.add(key)
        owner = catalog.get(key)
        if owner is None:
            continue          # no file owns it: the chain has reached its origin
        subject = (owner.get("sheet") or "").strip() or table
        found = mapping.claims_from(
            "hop_spec", owner["path"], owner["sheet"], subject,
            store.records(owner["path"], owner["sheet"], "hop_spec"))
        claims += found
        pairs.append((subject, owner["to_stage"]))
        queue += [c.source_table for c in found if c.source_table]
    return claims, pairs


def sql_claims(file_kinds, store):
    """Claims from a folder of CREATE scripts, one subject per file."""
    claims = []
    for path, kind in file_kinds.items():
        records = store.records(str(path), None, kind)
        # The subject is the object the statement creates. Taken from the
        # extraction rather than re-parsed, because that is the value
        # resolve_view has always used and the SQL ground truth was measured
        # against it; the CREATE line is the cross-check, not the source.
        subject = next((r.get("target_table") for r in records
                        if isinstance(r, dict) and r.get("target_table")), None)
        claims += mapping.claims_from(kind, str(path), None, subject, records)
    return claims


def doc_claims(store, paths, verbose=True):
    """Claims from prose documents, one call per SECTION.

    A document is split before it is read — see sections.py: the 138-page design
    document is 211,648 characters, twelve times the largest input this program
    has ever sent, against a file thirteen times smaller that already truncated.
    """
    claims, read = [], []
    for path in paths:
        try:
            parts = store.sections(str(path))
        except Exception as exc:
            read.append({"file": Path(path).name, "sections": 0,
                         "error": f"{type(exc).__name__}: {str(exc)[:120]}"})
            continue
        if verbose:
            print(f"  {Path(path).name}: {len(parts)} section(s)")
        found = 0
        for section_id, _ in parts:
            records = store.records(str(path), section_id, "doc_lineage")
            new = mapping.claims_from("doc_lineage", str(path), section_id,
                                      None, records)
            claims += new
            found += len(new)
        read.append({"file": Path(path).name, "sections": len(parts),
                     "claims": found})
    return claims, read


def assembler_diff(legacy, unified) -> dict:
    """Where the two assemblers disagree, keyed by the field each record is about.

    Reported rather than raised. The point of running both is to SHOW they
    agree; a difference is a finding to look at, and the run should still
    produce its dictionary while somebody looks.
    """
    def key(record):
        produced = assemble.produced_entry(record) or {}
        head = record["lineage"][0] if record.get("lineage") else {}
        return (produced.get("table"), produced.get("column"),
                head.get("table"), head.get("column"))

    def bucket(records):
        out = {}
        for record in records:
            out.setdefault(key(record), []).append(
                json.dumps(record, sort_keys=True, ensure_ascii=False))
        return {k: sorted(v) for k, v in out.items()}

    left, right = bucket(legacy), bucket(unified)
    only_legacy = sorted(set(left) - set(right))
    only_unified = sorted(set(right) - set(left))
    differing = [k for k in set(left) & set(right) if left[k] != right[k]]
    return {
        "legacy_records": len(legacy),
        "unified_records": len(unified),
        "only_in_legacy": len(only_legacy),
        "only_in_unified": len(only_unified),
        "differing": len(differing),
        "identical": len(set(left) & set(right)) - len(differing),
        "agrees": not (only_legacy or only_unified or differing),
        "examples": [f"{k[0]}.{k[1]} <- {k[2]}.{k[3]}"
                     for k in (only_legacy + only_unified + differing)[:5]],
    }


def build_views(args):
    """Lineage from CREATE scripts: one file per object, two stages.

    Each file is classified by the statement it opens with, before the store
    is asked for anything. That ordering is the point: an unrecognised script
    is rejected here, having cost nothing, rather than being read under a
    default prompt and returned as something it is not.
    """
    root = Path(args.sql)
    files = sorted(root.glob("*.sql")) if root.is_dir() else [root]
    if not files:
        print(f"No .sql files under {args.sql}"); sys.exit(1)
    store = RecordStore(load_schemas(), cache_path=args.cache)

    # Classify first, read second. No fallback kind: a file that matches no
    # registered statement is named in the report and skipped. Silently
    # reading it as a view is what let a CREATE TABLE through, and the cost of
    # that was not just a wrong label — declared_object found no view header,
    # so completeness switched itself off and the one check that catches a
    # truncated reply stopped running, without saying so.
    file_kinds, unrecognised = {}, []
    for path in files:
        kind = classify_sql(read_sql_text(str(path)))
        if kind is None:
            unrecognised.append(path)
        else:
            file_kinds[path] = kind
    counts = Counter(file_kinds.values())
    print(f"SQL: {len(files)} script(s) — "
          + ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
          + (f", {len(unrecognised)} unrecognised" if unrecognised else ""))
    for path in unrecognised:
        print(f"  SKIPPED {path.name}: no recognised CREATE statement")

    records = []
    for path, kind in file_kinds.items():
        records += assemble.resolve_view(str(path), store, kind)
    records = assemble.chain_views(records)

    # The unified assembler over the same store — no extra API call, because
    # every file it asks for has already been read.
    assembler = getattr(args, "assembler", "legacy") or "legacy"
    stage_audit = diff_report = None
    if assembler != "legacy":
        claims = sql_claims(file_kinds, store)
        derived = order.derive(claims)
        # chain_depth=1 because a .sql file asserts ONE hop and that is what the
        # hand-built SQL ground truth scores. The longer chain is still followed
        # — chain_views records it as resolved_source, in the "Ultimate Source"
        # and "Via" columns the manual sheet actually has. The difference
        # between the two modes is presentational, and this is the parameter
        # that says so.
        unified = assemble.chain_views(assemble.resolve_universal(
            claims, order.stage_names(derived), derived.depths, chain_depth=1))
        # Does a view's position in the graph agree with the statement it was
        # classified by? Two independent answers to the same question.
        stage_audit = order.audit(
            derived, [(c.subject_table, kinds.get(c.kind).stage) for c in claims],
            assemble.stages_in(unified))
        if assembler == "both":
            diff_report = assembler_diff(records, unified)
        else:
            records = unified

    source_errors = [f"{Path(r['path']).name}: {e}"
                     for r in store.reports for e in r.get("errors", [])]
    source_errors += [
        f"{p.name}: opens with no recognised CREATE statement "
        f"({sorted(kinds.statements())}); not read." for p in unrecognised]
    chained = sum(1 for r in records if r.get("resolved_source"))
    # The stages are read off the records, exactly as the archive mode reads
    # them off its layout. They used to come from a ["source", "view"]
    # constant, which was a claim about what a folder of .sql files can hold
    # rather than a reading of what this one did hold — and a constant cannot
    # be wrong loudly. A view-only folder still yields ["source", "view"].
    stages = assemble.stages_in(records)
    # Each produced stage is its own little pipeline, and completeness is
    # asked per group rather than against the union of them. A views-only
    # folder has exactly one group, [source, view], so this changes nothing
    # there — which is the point: it only starts mattering once a folder holds
    # more than one kind of statement, and by then it is too late to add.
    groups = assemble.records_by_produced_stage(records)
    stages_for = {stage: assemble.stages_in(rs) for stage, rs in groups.items()}
    report = {
        "mode": "sql", "files": [f.name for f in files],
        # Which statement each file was read as. A folder is no longer assumed
        # to be all one thing, so the report has to say, per file, what it was
        # taken for — that is the claim a reviewer can check against the file.
        "file_kinds": {p.name: k for p, k in file_kinds.items()},
        "unrecognised_files": [p.name for p in unrecognised],
        "files_read": len(store.reports), "files_converted": store.converted,
        "sources": store.reports,
        "coverage": coverage_metrics(records, stages, stages_for),
        "chain_diagnostics": chain_diagnostics(records, stages, stages_for),
        "views_chained_to_origin": chained,
        "source_errors": source_errors,
    }
    if stage_audit:
        report["stage_order"] = stage_audit
    if diff_report:
        report["assembler_diff"] = diff_report
    # Per-stage detail only when there IS more than one; with a single kind it
    # would be a verbatim copy of "coverage" sitting under a second name,
    # which invites a reader to look for a difference that cannot exist.
    if len(groups) > 1:
        report["coverage_by_stage"] = {
            stage: coverage_metrics(rs, stages_for[stage])
            for stage, rs in groups.items()}

    blocks = [("View chaining:", {"resolved_through_another_view": chained})]
    if diff_report:
        blocks.append(("Assembler comparison (legacy vs unified):", {
            "agrees": diff_report["agrees"],
            "identical": diff_report["identical"],
            "differing": diff_report["differing"],
            "only_legacy": diff_report["only_in_legacy"],
            "only_unified": diff_report["only_in_unified"]}))
    if len(groups) > 1:
        blocks.append(("Per produced stage (each judged on its own stages):", {
            stage: f"{len(rs)} records, "
                   f"{report['coverage_by_stage'][stage]['complete_chains']} complete"
            for stage, rs in groups.items()}))
    # SQL mode counts and reports descriptions, but its workbook has no column
    # for them yet (VIEW_COLS predates this). Say so rather than silently
    # accepting the file and showing nothing.
    overlay = load_overlay(args, stages)
    if overlay is not None:
        print("  note: the SQL workbook has no description column yet; the "
              "descriptions are reported but not written to views.xlsx")
    finish(records, report, args, emit.write_view_workbook, blocks,
           overlay=overlay)


def build_docs(args):
    """A dictionary from prose alone — the case that used to come back empty.

    Point the old program at a folder of PDFs and it produced nothing: three of
    five kinds made lineage, and the one that read documents made descriptions
    only and never reached the assembler. So a PDF could add meaning to a field
    Excel or SQL had already found, but could not discover a field or contribute
    a chain.

    Nothing here is special-cased for prose. The documents are split into
    sections, each section is read on its own under the doc_lineage contract,
    and the resulting claims go through the SAME pool, the same order
    derivation and the same assembler the other two modes now use. What differs
    is only what a document can honestly offer: no completeness anchor, and a
    subject read from a caption rather than from a sheet name.
    """
    root = Path(args.docs)
    if root.is_dir():
        docs = [p for p in sorted(root.rglob("*"))
                if p.is_file() and readers.for_path(p)
                and p.suffix.lower() not in (".sql", ".txt")]
    else:
        docs = [root]
    if not docs:
        print(f"No readable documents under {args.docs}. "
              f"This build reads: {sorted(readers.readable_extensions())}")
        sys.exit(1)

    store = RecordStore(load_schemas(), cache_path=args.cache)
    print(f"Documents: {len(docs)} file(s)")
    claims, read = doc_claims(store, docs)

    derived = order.derive(claims)
    # No layout to borrow names from — this is the corpus that never had one,
    # and order.py is what replaces it. Names come from the tables themselves
    # where they share a prefix, and are positional where they do not.
    stages = order.stage_names(derived)
    records = assemble.chain_views(
        assemble.resolve_universal(claims, stages, derived.depths))

    source_errors = [f"{Path(r['path']).name} [{r['sheet']}]: {e}"
                     for r in store.reports for e in r.get("errors", [])]
    groups = assemble.records_by_produced_stage(records)
    stages_for = {stage: assemble.stages_in(rs) for stage, rs in groups.items()}
    untrusted = mapping.untrusted(claims)
    report = {
        "mode": "docs",
        "documents": read,
        "files_read": len(store.reports),
        "files_converted": store.converted,
        "sources": store.reports,
        "claims": len(claims),
        # How much of this dictionary rests on a table name a model read out of
        # a caption rather than on a file fact. For prose that is all of it, and
        # saying so is the point: the other two modes stamp their subject from a
        # sheet name or a CREATE line, and a reader is entitled to know that
        # this one cannot.
        "subject_from_text": len(untrusted),
        "stage_order": order.audit(derived, [], stages),
        "coverage": coverage_metrics(records, stages, stages_for),
        "chain_diagnostics": chain_diagnostics(records, stages, stages_for),
        "source_errors": source_errors,
    }

    blocks = [("Documents:", {
        "files": len(docs), "sections": sum(d.get("sections", 0) for d in read),
        "mapping claims": len(claims),
        "subject read from text": f"{len(untrusted)}/{len(claims)}"}),
        ("Stage order (derived — prose declares none):", {
            "stages": " -> ".join(stages) or "(none)",
            "cycles_broken": report["stage_order"]["cycles_broken"]})]
    finish(records, report, args, emit.write_workbook, blocks,
           overlay=load_overlay(args, stages))


def run(args):
    """Execute one run. Separate from argument parsing so the GUI can call it
    with the same options the command line would produce."""
    # The survey describes a FOLDER and the rules document describes the
    # FORMATS. Neither is a run, so both come before a mode is demanded.
    if getattr(args, "survey", None):
        facts = survey.survey(args.survey)
        proposal = survey.propose(facts)
        print(survey.render(facts, proposal))
        if getattr(args, "survey_out", None):
            path = survey.write_proposal(proposal, args.survey_out)
            print(f"\nProposal written to {path}")
            print("Read it, correct the stage ORDER if it is wrong — that is "
                  "the part no single file can verify — then run with "
                  f"--layout {path}")
        else:
            print("\nNothing has been applied. Re-run with --survey-out FILE "
                  "to save this, or pass an existing layout with --layout.")
        if not (args.sql or args.archive or getattr(args, 'docs', None)):
            return

    # The rules document describes the FORMATS, not a run, so it needs neither
    # an archive nor a mode and is emitted before either is demanded.
    if getattr(args, "rules_doc", None):
        path, count = rules_doc.write(SCHEMA_DIR, args.rules_doc)
        excel = len(rules_doc.rows(SCHEMA_DIR,
                                   only=[k for k, v in kinds.KINDS.items()
                                         if v.reader == kinds.EXCEL]))
        print(f"Rules document: {count} rule(s) across "
              f"{len(kinds.KINDS)} format(s), {excel} of them Excel -> {path}")
        if not (args.sql or args.archive or getattr(args, 'docs', None)):
            return

    # Generating a contract describes a FORMAT, not a run, so it needs neither
    # an archive nor a mode — the same standing --survey and --rules-doc have.
    if getattr(args, "generate_template", None):
        target = Path(OUT_DIR) / "generated"
        target.mkdir(parents=True, exist_ok=True)
        name = Path(args.generate_template[0]).stem.replace(" ", "_")[:40]
        path = target / f"{name}_template.py"
        if not templates.templategen_available():
            print("Cannot generate a contract: docling-graph is not installed "
                  "in this build. It pulls docling and LiteLLM behind it, and "
                  "the small deployment ships without them on purpose.")
            sys.exit(1)
        try:
            result = templates.generate_module(args.generate_template, name, path)
        except Exception as exc:
            print(f"Template generation failed: {type(exc).__name__}: {exc}")
            sys.exit(1)
        print(f"Verification passed: {result.verification.passed}")
        if result.gaps:
            print(f"  {len(result.gaps)} gap(s) the induction could not settle:")
            for gap in result.gaps[:5]:
                print(f"    - {gap}")
        print(f"  written to: {result.written_path or '(nothing — verification failed)'}")
        print("\nRead it before adopting it. A generated contract goes into the "
              "prompt verbatim, so it changes what every extraction under it "
              "means; templates.register_generated is the deliberate step that "
              "puts its hash into the cache key.")
        if not (args.sql or args.archive or getattr(args, 'docs', None)):
            return

    apply_mode_defaults(args)
    check_output_paths(args)
    if args.sql:
        return build_views(args)
    if getattr(args, "docs", None):
        return build_docs(args)
    if not args.archive:
        print("Give one of --archive DIR, --sql DIR or --docs DIR"); sys.exit(1)
    try:
        layout = load_layout(args.archive, args.layout)
    except (LayoutError, ValueError) as exc:
        print(f"Bad archive layout: {exc}"); sys.exit(1)

    catalog = build_catalog(args.archive, layout)
    if not catalog:
        print(f"No hop specs found under {args.archive}. Expected folders: "
              f"{', '.join(h['dir'] for h in layout['hops'])}"); sys.exit(1)

    # By default build the tables produced by the last hop — the end of the
    # pipeline as this layout describes it.
    last_dir = final_hop_dir(layout)
    targets = [t.strip().upper() for t in args.table] or sorted(
        t for t, v in catalog.items() if v["stage_dir"] == last_dir)
    missing = [t for t in targets if t not in catalog]
    if missing:
        print("Not in the archive: " + ", ".join(missing)); sys.exit(1)

    store = RecordStore(load_schemas(), cache_path=args.cache,
                        anchors=header_anchors(layout))
    cloud_path = find_cloud_workbook(args.archive, layout)
    print(f"Archive: {len(catalog)} tables indexed | building {len(targets)}")

    cloud_index = {}
    if cloud_path:
        # A cloud sheet may drop the warehouse prefix: DWH_TXN_HISTORY is
        # filed under "TXN_HISTORY". Accept every configured spelling.
        wanted = set(targets)
        for prefix in table_prefixes(layout):
            wanted |= {t[len(prefix):] for t in targets if t.startswith(prefix.upper())}
        sheets = {t: s for t, s in cloud_sheets(cloud_path).items() if t in wanted}
        if sheets:
            cloud_index = assemble.build_cloud_index(cloud_path, sheets, store)

    records = []
    for table in targets:
        records += assemble.resolve_table(table, catalog, store, cloud_index,
                                          cloud_stage(layout), table_prefixes(layout))

    # The unified assembler, run alongside the legacy one or in its place. Both
    # read the SAME store, so running both costs no extra API call — the second
    # pass is served entirely from memory.
    assembler = getattr(args, "assembler", "legacy") or "legacy"
    stage_audit = diff_report = None
    if assembler != "legacy":
        claims, pairs = archive_claims(catalog, store, targets)
        derived = order.derive(claims)
        # The DECLARED names still label the stages. compare.py keys every
        # archive row on dwh_table/dwh_column and lays its columns out by stage
        # position, so a derived label would score zero for reasons that have
        # nothing to do with lineage. What the derivation is for here is the
        # audit below — the first check in this program that can catch a wrong
        # stage ORDER, which passes fidelity and completeness today.
        stages = order.stage_names(derived, layout["stages"])
        unified = assemble.resolve_universal(
            claims, stages, derived.depths, subjects=targets,
            cloud_index=cloud_index, cloud_stage=cloud_stage(layout),
            table_prefixes=table_prefixes(layout))
        stage_audit = order.audit(derived, pairs, layout["stages"])
        if assembler == "both":
            diff_report = assembler_diff(records, unified)
        else:
            records = unified

    # Per-source checkpoints, gathered from every file the run actually read.
    source_errors = [f"{Path(r['path']).name} [{r['sheet']}]: {e}"
                     for r in store.reports for e in r.get("errors", [])]
    report = {
        # Stated, not inferred. build_views has always set "mode": "sql" and
        # this side set nothing, so anything reading a report back had to guess
        # the mode from a filename — and both modes write output.json when the
        # app runs them.
        "mode": "archive",
        "targets": targets,
        "files_read": len(store.reports),
        "files_converted": store.converted,
        "sources": store.reports,
        "coverage": coverage_metrics(records, layout["stages"]),
        "chain_diagnostics": chain_diagnostics(records, layout["stages"]),
        "source_errors": source_errors,
    }

    if stage_audit:
        report["stage_order"] = stage_audit
    if diff_report:
        report["assembler_diff"] = diff_report

    chain = report["chain_diagnostics"]
    # The overlay is loaded against the LAYOUT's stage list, which is what the
    # field keys were computed under.
    overlay = load_overlay(args, layout["stages"])
    emitter = emit.write_workbook
    if overlay is not None:
        emitter = lambda recs, path: emit.write_workbook(recs, path,
                                                         overlay=overlay)
    blocks = []
    if stage_audit:
        blocks.append(("Stage order (derived from the claims, not declared):", {
            "derived": " -> ".join(stage_audit["derived_order"]) or "(none)",
            "declared": " -> ".join(stage_audit["declared_order_of_produced"]) or "(none)",
            "agrees": stage_audit["agrees"],
            "conflicts": stage_audit["conflict_count"],
            "cycles_broken": stage_audit["cycles_broken"]}))
    if diff_report:
        blocks.append(("Assembler comparison (legacy vs unified):", {
            "agrees": diff_report["agrees"],
            "identical": diff_report["identical"],
            "differing": diff_report["differing"],
            "only_legacy": diff_report["only_in_legacy"],
            "only_unified": diff_report["only_in_unified"]}))
    finish(records, report, args, emitter,
           blocks + [("Chain diagnostics:", {
               "complete_chains": f"{chain['complete_chains']}/{chain['chains']}",
               "unmatched_tails": chain["unmatched_tails"]["count"],
               "unmatched_heads": chain["unmatched_heads"]["count"]})],
           overlay=overlay)

def main():
    run(parse_args())


if __name__ == "__main__":
    main()
