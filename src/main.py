import argparse, json, sys
from pathlib import Path

import assemble
import emit
import kinds
from catalog import build_catalog, cloud_sheets, find_cloud_workbook
from layout import (LayoutError, cloud_stage, final_hop_dir, load_layout,
                    table_prefixes)
from store import RecordStore
from validate import chain_diagnostics, coverage_metrics

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schemas"


# Which schema file belongs to which source kind is declared once, in
# kinds.py, beside everything else about that kind. SCHEMA_DIR stays a module
# global read at call time, because the app corrects it after import: a frozen
# bundle does not preserve the path main.py computes from its own __file__.
def load_schemas():
    return {kind: json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))
            for kind, filename in kinds.schema_files().items()}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python src/main.py",
        description="Assemble a data dictionary from an archive of hop specs.")
    parser.add_argument("--sql", metavar="DIR_OR_FILE",
                        help="folder of CREATE VIEW .sql scripts (or one file). "
                             "Builds view lineage instead of an archive chain.")
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
    parser.add_argument("--out", default="output.json")
    parser.add_argument("--xlsx", default="output.xlsx",
                        help="same dictionary in the hand-built layout.")
    parser.add_argument("--report", default="report.json")
    parser.add_argument("--cache", default=".cache/records.json",
                        help="extraction cache; delete it to force re-reading.")
    return parser.parse_args(argv)


def print_block(title, mapping):
    print(f"\n{title}")
    for name, value in mapping.items():
        print(f"  {name}: {value}")


def finish(records, report, args, emitter, extra_blocks=()):
    """Report, print and write — identical for every mode.

    Only the spreadsheet layout and the mode-specific block of numbers differ,
    so both arrive as arguments rather than as a second copy of this code.
    """
    print_block("Coverage (what a reviewer should look at):", report["coverage"])
    for title, mapping in extra_blocks:
        print_block(title, mapping)

    print(f"\nFiles read: {report['files_read']} "
          f"({report['files_converted']} converted, rest cached)")
    errors = report.get("source_errors", [])
    if errors:
        print(f"Extraction problems: {len(errors)}")
        for error in errors[:10]:
            print(f"  - {error}")

    Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
    Path(args.out).write_text(json.dumps(records, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    emitter(records, args.xlsx)
    print(f"\nWrote {len(records)} records -> {args.out}, {args.xlsx}, {args.report}")


def build_views(args):
    """Lineage from CREATE VIEW scripts: one file per view, two stages."""
    root = Path(args.sql)
    files = sorted(root.glob("*.sql")) if root.is_dir() else [root]
    if not files:
        print(f"No .sql files under {args.sql}"); sys.exit(1)
    store = RecordStore(load_schemas(), cache_path=args.cache)
    print(f"SQL: {len(files)} view script(s)")

    records = []
    for path in files:
        records += assemble.resolve_view(str(path), store)
    records = assemble.chain_views(records)

    source_errors = [f"{Path(r['path']).name}: {e}"
                     for r in store.reports for e in r.get("errors", [])]
    chained = sum(1 for r in records if r.get("resolved_source"))
    report = {
        "mode": "sql", "files": [f.name for f in files],
        "files_read": len(store.reports), "files_converted": store.converted,
        "sources": store.reports,
        "coverage": coverage_metrics(records, assemble.VIEW_STAGES),
        "chain_diagnostics": chain_diagnostics(records, assemble.VIEW_STAGES),
        "views_chained_to_origin": chained,
        "source_errors": source_errors,
    }
    finish(records, report, args, emit.write_view_workbook,
           [("View chaining:", {"resolved_through_another_view": chained})])


def run(args):
    """Execute one run. Separate from argument parsing so the GUI can call it
    with the same options the command line would produce."""
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
        "targets": targets,
        "files_read": len(store.reports),
        "files_converted": store.converted,
        "sources": store.reports,
        "coverage": coverage_metrics(records, layout["stages"]),
        "chain_diagnostics": chain_diagnostics(records, layout["stages"]),
        "source_errors": source_errors,
    }

    chain = report["chain_diagnostics"]
    finish(records, report, args, emit.write_workbook,
           [("Chain diagnostics:", {
               "complete_chains": f"{chain['complete_chains']}/{chain['chains']}",
               "unmatched_tails": chain["unmatched_tails"]["count"],
               "unmatched_heads": chain["unmatched_heads"]["count"]})])

def main():
    run(parse_args())


if __name__ == "__main__":
    main()
