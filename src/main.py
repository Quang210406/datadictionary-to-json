import argparse, json, sys
from collections import Counter
from pathlib import Path

import assemble
import emit
import entities
import kinds
from catalog import build_catalog, cloud_sheets, find_cloud_workbook
import readers
from extract import classify_sql, read_sql_text
from layout import (LayoutError, cloud_stage, final_hop_dir, load_layout,
                    table_prefixes)
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
}


def apply_mode_defaults(args):
    """Fill in whichever output paths the caller left unset, per mode.

    Uses getattr/setattr rather than reading attributes directly so it also
    works on a namespace built by hand — the desktop app assembles one and
    sets all four itself, and anything it has already set is left alone.
    """
    for field, value in MODE_DEFAULTS["sql" if args.sql else "archive"].items():
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
    # Per-stage detail only when there IS more than one; with a single kind it
    # would be a verbatim copy of "coverage" sitting under a second name,
    # which invites a reader to look for a difference that cannot exist.
    if len(groups) > 1:
        report["coverage_by_stage"] = {
            stage: coverage_metrics(rs, stages_for[stage])
            for stage, rs in groups.items()}

    blocks = [("View chaining:", {"resolved_through_another_view": chained})]
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
        if not (args.sql or args.archive):
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
        if not (args.sql or args.archive):
            return

    apply_mode_defaults(args)
    check_output_paths(args)
    if args.sql:
        return build_views(args)
    if not args.archive:
        print("Give either --archive DIR or --sql DIR"); sys.exit(1)
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

    store = RecordStore(load_schemas(), cache_path=args.cache)
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

    chain = report["chain_diagnostics"]
    # The overlay is loaded against the LAYOUT's stage list, which is what the
    # field keys were computed under.
    overlay = load_overlay(args, layout["stages"])
    emitter = emit.write_workbook
    if overlay is not None:
        emitter = lambda recs, path: emit.write_workbook(recs, path,
                                                         overlay=overlay)
    finish(records, report, args, emitter,
           [("Chain diagnostics:", {
               "complete_chains": f"{chain['complete_chains']}/{chain['chains']}",
               "unmatched_tails": chain["unmatched_tails"]["count"],
               "unmatched_heads": chain["unmatched_heads"]["count"]})],
           overlay=overlay)

def main():
    run(parse_args())


if __name__ == "__main__":
    main()
