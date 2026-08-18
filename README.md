# Hecate

Builds a data dictionary — every field, where it came from, and how it was
transformed — from documentation that was never designed to be machine-read.

An AI agent reads each messy source file into flat records; plain Python joins
those records into lineage. **That split is the point of the design**: when a
result is wrong you can tell whether extraction or assembly caused it, and the
joins can be trusted because they were computed, not generated.

---

## The problem

A data platform moves a field through stages — a source system, a staging
layer, a warehouse, a cloud copy — and each hop is documented separately.

**Documentation is organised per table, not per stage.** There is no
"source-to-staging document"; there are 74 of them, one per table. A single
field's journey spans three or four workbooks, none of which references the
others.

**The files are hand-maintained, so they are inconsistent.** Real examples: 13
rows of metadata above the actual column header; a "Transformation Type" column
empty in 97.6% of rows while the real rule sits in a "Notes" column; row cells
naming the *source* table under a *target* heading; several source tables
stacked in one cell; business rules written as prose.

**Datatypes change along the way** — in about 10% of rows the type or size
differs between the two ends of a single hop.

By hand, one field takes minutes. There are thousands of fields.

---

## Quick start

```bash
pip install pandas openpyxl jsonschema python-dotenv google-genai
```

`.env` in the project root:

```
GEMINI_API_KEY=your-key-here
```

### Excel archive

```bash
python src/main.py --archive path/to/archive --table TARGET_TABLE
```

Omit `--table` to build every table produced by the last hop.

### SQL views

```bash
python src/main.py --sql path/to/sql/folder --out views.json --xlsx views.xlsx
```

### Score against a hand-built reference

```bash
python src/compare.py ground_truth.xlsx output.json          # Excel mode
python src/compare.py ground_truth.xlsx views.json --views   # SQL mode
```

Extractions are cached **by file content**, so re-runs are free, a run that
failed part-way retries only what failed, and a cache stays valid when the
project moves machine.

---

## The two modes

| | Excel archive | SQL views |
|---|---|---|
| Lineage lives | across many files | inside one file |
| Stages | 4: source → staging → dwh → cloud | 2: source → view |
| Resolution | walks a catalog backwards | reads one file |
| n→1 | rare | normal |
| Datatype/size | stated at both ends of each hop | not stated at all |

### How Excel mode resolves a field

The archive stores one workbook **per table**, so a stage is not a file you can
name. The program indexes every table first, then walks each field backwards:

    open the file that owns the target table
    read the row -> it names a source table and column
    look that source table up in the index
    open the file that owns IT, read its row for that column
    repeat until no file owns the table -> that is the origin
    finally look the target up in the final-stage workbook

Walking *backwards* is what makes this reliable. Each row's "Target Table Name"
cell frequently holds the source table copied down the column; because
resolution arrives at each file by name lookup and only reads its *source*
side, that unreliable cell is never consulted. **The sheet name is
authoritative, the row cell is not.**

### How SQL mode resolves a view

A view stores no data — it is a saved query — so its definition states exactly
where each column comes from. One file is the whole lineage: read the declared
column list, then read the SELECT expression filling each one.

Where a view reads another view, `chain_views()` follows it to the physical
origin and records that as `resolved_source` rather than lengthening the chain.
The extraction still asserts only the one hop a single file can justify.

---

## Configuring a different archive

Folder names, stage names and the final-stage workbook's filename live in
`src/layout.py`, not scattered through the code. To point the tool at a
differently-shaped archive, drop an `archive.json` beside its folders
(`archive.example.json` in this repo is a commented template):

```json
{
  "stages": ["source", "staging", "dwh", "cloud"],
  "hops": [
    {"dir": "SRC_STGDIH",    "from": "source",  "to": "staging"},
    {"dir": "STGDIH_DWHDIH", "from": "staging", "to": "dwh"}
  ],
  "cloud": {"glob": "*Mapping*CLOUD*.xlsx", "stage": "cloud",
            "table_prefixes": ["DWH_"]},
  "non_hop_sheets": ["DDL"]
}
```

Resolution order: `--layout FILE` → `archive.json` inside the archive → the
built-in default. A layout naming a stage that does not exist is rejected with
a message rather than quietly producing unrecognised stage labels.

Everything downstream — the spreadsheet's column groups, the coverage metrics,
the comparison offsets — derives the stage list from the **records themselves**,
so a five-stage archive needs no further changes.

---

## Modules

Read in this order; it is also the order data flows.

| Module | Role | AI? |
|---|---|---|
| `layout.py` | What shape is this archive | no |
| `catalog.py` | Indexes the archive: `{table → file, sheet, stages}` | no |
| `extract.py` | Sheet → CSV, or `.sql` → text. Finds the completeness anchor | no |
| `agent.py` | **The only AI.** One prompt per source kind | **yes** |
| `store.py` | Converts a file on demand, caches it, isolates failures | no |
| `assemble.py` | Builds lineage: `resolve_table`, `resolve_view`, `chain_views` | no |
| `validate.py` | Every check and every number | no |
| `emit.py` | Writes the reviewable spreadsheet | no |
| `compare.py` | Scores output against a hand-built reference | no |
| `main.py` | Orchestration only | no |

### Functions that carry weight

**`catalog.build_catalog(dir, layout)`** — a file whose *name* matches the table
beats one that merely contains a *sheet* of that name; some workbooks carry a
copy-pasted sheet title from another table, and resolving through those silently
reads the wrong table. Stamps each entry with its own stage names, so assembly
never looks up a folder.

**`extract.expected_row_count`** / **`extract.declared_view`** — the
completeness anchors. A spreadsheet says how many rows it has; a view declares
how many columns. Without these the completeness check is silently skipped.

**`store.RecordStore.records(path, sheet, kind)`** — the whole interface between
assembly and anything expensive. In-memory memo, then disk cache, then extract
and convert. On one real run assembly asked for a file's rows **19 times and it
was read 3 times**. A failed conversion is recorded and returns `[]`: one
transient API error must not destroy a 90-file run.

**`assemble.field_key(table, column)`** — the single definition of "the same
field". Strips and upper-cases **for matching only**; emitted values keep the
source's own spelling and padding.

**`assemble.stages_in(records)`** — the stage list, read off the records. Emit,
compare and coverage all use it, so none of them needs to be told the shape.

---

## Output

**One record is one (target field, source field) pair** — not one target field.
That is what lets a field with ten sources exist as ten records sharing a
target, instead of values stuffed into one cell.

```json
{ "description": "business meaning, when a source states one",
  "lineage": [
    { "stage": "staging", "table": "...", "column": "...",
      "datatype": "NUMERIC", "size": "6",
      "offline_path": "which file said so",
      "sources": [] },
    { "stage": "dwh", "table": "...", "column": "...",
      "datatype": "VARCHAR2", "size": "8",
      "offline_path": "which file said so",
      "sources": [ { "table": "...", "column": "...",
                     "transformation_logic": "the rule as written",
                     "role": "value" } ] }
  ] }
```

`offline_path` on each entry is the evidence trail. `sources` hangs off the
stage that was *produced*; the origin stage has an empty list. `role`
distinguishes a value source from a table joined only to locate the row, or a
column tested by a rule but never copied.

Three files per run: **`output.json`** (the dictionary), **`output.xlsx`** (same
records, laid out for review by eye), **`report.json`** (per-file validation,
coverage, chain diagnostics, failures). The JSON and the spreadsheet are
siblings written from the same in-memory list.

---

## Checks

| Check | Question | Fatal |
|---|---|---|
| Input | Does the file have data / a SELECT? | yes |
| Shape | Does the agent's reply match the schema? | yes |
| Completeness | distinct target fields == input rows (or declared columns)? | yes |
| Fidelity | Does every table/column name appear verbatim in the source text? | yes |
| Coverage | How much got filled, per stage? | no |
| Chain diagnostics | Where did a chain start or stop early? | no |

**Fidelity is the strongest guarantee.** Every identifier is checked
character-for-character against the text the agent was given. Because each call
sees exactly one file, an invented cross-file link is impossible by construction
and an invented name is caught mechanically on every run.

**Completeness counts distinct target fields, not records** — one input row can
legitimately produce several records under n→1. The report gives
`fields_covered` and `records_emitted` separately, because a metric that isn't
the thing being checked trains people to ignore the report.

The last two are reported and never fail a run. A gap is often the honest
answer, and only someone who knows the platform can say whether a blank is a
defect — so the tool quantifies it and leaves the call to a person.

---

## Accuracy

Scored against dictionaries built by hand from the same source files.

| | Rows matched | Field accuracy |
|---|---|---|
| Excel archive | 20/20 | **98.4%** |
| SQL views | 24/24 | **99.3%** |

On the SQL side, all 16 views extracted with **2492/2492 fidelity** and every
declared column covered.

---

## Known gaps
- **`lineage.json` is not enforced** — the assembled output has no schema check.
- **`DWH_TEMP_PARTY v2.xlsx`** yields 54 distinct target fields from 56 rows;
  two go missing. Not yet investigated.
- **Extraction depends on API quota.** Failed files are reported and the run
  continues with a partial dictionary rather than nothing.
