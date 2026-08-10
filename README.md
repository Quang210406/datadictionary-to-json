# Hecate

Builds a data dictionary - every field, where it came from, and how it was
transformed.

An AI agent reads each messy source file into flat records; plain Python joins
those records into lineage. **That split is the point of the design**: when a
result is wrong you can tell whether extraction or assembly caused it, and the
joins can be verified because they were computed, not generated.

---

## The problem

A data platform moves a field through stages — a source system, a staging
layer, a warehouse, a cloud copy — and each hop is documented separately. Three
things make reassembling that painful:

**Documentation is organised per table, not per stage.** There is no
"source-to-staging document"; there are 74 of them, one per table. A single
field's journey is spread across three or four workbooks, none of which
references the others.

**The files are hand-maintained, so they are inconsistent.** Real examples: 13
rows of metadata above the actual column header; a "Transformation Type" column
that is empty in 97.6% of rows while the real rule lives in a "Notes" column;
row cells that name the *source* table under a *target* heading; several source
tables stacked inside one cell.

**Datatypes change along the way.** 

Done by hand, one field takes minutes. There are thousands of fields.

---

## Quick start (assuming we use a free gemini api key)

```bash
pip install pandas openpyxl jsonschema python-dotenv google-genai
```

Create `.env` in the project root:

```
GEMINI_API_KEY=your-key-here
```

### Mode 1 — mapping archive (Excel)

```bash
python src/main.py --archive path/to/archive --table TARGET_TABLE
```

### Mode 2 — SQL views

```bash
python src/main.py --sql path/to/sql/folder --out views.json --xlsx views.xlsx
```

### Score either against a hand-built reference

```bash
python src/compare.py ground_truth.xlsx output.json          # Excel mode
python src/compare.py ground_truth.xlsx views.json --views   # SQL mode
```

Extractions are cached by file path and modification time, so re-runs are
free and a run that failed part-way only retries what failed.

---

## The two modes

They exist because the two kinds of source have genuinely different shapes.

| | Archive (Excel) | SQL views |
|---|---|---|
| Lineage lives | across many files | inside one file |
| Stages | 4: source → staging → dwh → cloud | 2: source → view |
| How it resolves | walks a catalog backwards | reads one file |
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
    finally look the target up in the cloud reference

Walking *backwards* is what makes this reliable. Each row's "Target Table Name"
cell frequently holds the source table copied down the column; because
resolution arrives at each file by name lookup and only reads its *source*
side, that unreliable cell is never consulted. **The sheet name is
authoritative, the row cell is not.**

### How SQL mode resolves a view

A view stores no data — it is a saved query — so its definition states exactly
where each column comes from. One file is the whole lineage: read the declared
column list, then read the SELECT expression that fills each one.

Where a view reads another view, `chain_views()` follows it to the physical
origin and records that as `resolved_source`, rather than lengthening the
chain. The extraction still asserts only one hop — which is what a single file
can justify — and the chain is derived separately in Python.

---

## Module reference

Read them in this order; that is also the order data flows.

| Module | Role | AI? |
|---|---|---|
| `catalog.py` | Indexes the archive: `{table → file, sheet}` | no |
| `extract.py` | Reads a sheet as a raw grid → CSV, or a `.sql` file as text. Finds the completeness anchor | no |
| `agent.py` | **The only AI.** One prompt per source kind | **yes** |
| `store.py` | Converts a file on demand, caches it, isolates failures | no |
| `assemble.py` | Builds lineage: `resolve_table` walks the archive, `resolve_view` reads a view, `chain_views` follows view-to-view | no |
| `validate.py` | Every check and every number | no |
| `emit.py` | Writes the reviewable spreadsheet | no |
| `compare.py` | Scores output against a hand-built reference | no |
| `main.py` | Orchestration only — no logic of its own | no |

### The functions that matter

**`catalog.build_catalog(dir)`** — scans the hop folders. A file whose *name*
matches the table beats one that merely contains a *sheet* of that name; some
workbooks carry a copy-pasted sheet title from another table, and resolving
through those silently reads the wrong table.

**`extract.expected_row_count(df, kind)`** / **`extract.declared_view(text)`** —
the completeness anchors. A spreadsheet says how many data rows it has; a view
declares how many columns it has. Without these the completeness check is
silently skipped.

**`store.RecordStore.records(path, sheet, kind)`** — the whole interface
between assembly and everything expensive. Checks an in-memory memo, then a
disk cache, then extracts and converts. On one real run assembly asked for a
file's rows **19 times and it was read 3 times**. A failed conversion is
recorded and returns `[]` rather than raising: one transient API error must not
destroy a 90-file run.

**`assemble.field_key(table, column)`** — the single definition of "the same
field". Every match in the project goes through it. Strips and upper-cases **for
matching only** — the emitted values keep the source's own spelling and padding.

**`assemble.resolve_table(...)`** / **`assemble.resolve_view(...)`** — the two
resolvers. Both produce the same record shape.

**`validate.validate_output(result, expected, schema, text)`** — bundles the
three fatal checks and produces the metrics from the same pass, so the numbers
can never disagree with the pass/fail decision.

---

## Schemas

`schemas/` holds one contract per source kind. Two conventions run through all
of them:

- **Required but nullable.** Every key is in `required`, with a `null` type
  alternative. The agent always emits the same key set, so an unknown value is
  an explicit `null` rather than a missing key.
- **`additionalProperties: false`**, so an invented field is a hard error.

| Schema | One record is | Key fields |
|---|---|---|
| `hop_record.json` | one row of a mapping spec | target/source table+column+datatype+size, transformation, `source_role` |
| `view_record.json` | one (declared column, source) pair in a view | target table+column, source schema+table+column+alias, `source_role`, transformation |
| `cloud_record.json` | one row of the cloud reference | table, column, datatype, size, nullable, **description** |
| `ddl_record.json` | one column of a standalone DDL sheet | *currently unused* |
| `lineage.json` | the assembled shape | *currently not enforced — see Known gaps* |

`view_record` deliberately reuses `hop_record`'s field names where the meaning
matches, so the completeness and fidelity checks work on both without special
cases.

### `source_role`

`value` (its data becomes the target), `join` (a table used only to locate the
row), `condition` (tested by a rule, never copied). Without this a derived flag
would appear to "come from" ten columns it merely tests.

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

`lineage` is the field's journey in stage order. `offline_path` on each entry is
the evidence trail — which file justified that stage. `sources` hangs off the
stage that was *produced*; the origin stage has an empty list.

Three files come out of a run:

- **`output.json`** — the dictionary
- **`output.xlsx`** — the same records laid out for review by eye
- **`report.json`** — how the run went: per-file validation, coverage, chain
  diagnostics, and any files that failed to read

`output.json` and `output.xlsx` are siblings written from the same in-memory
list; the spreadsheet is not converted from the JSON.

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

**Fidelity is the strongest guarantee.** Every identifier in the output is
checked character-for-character against the text the agent was given. Because
each AI call sees exactly one file, an invented cross-file link is impossible
by construction and an invented name is caught mechanically on every run.

**Completeness counts distinct target fields, not records**, because one input
row can legitimately produce several records under n→1.

The last two are reported and never fail a run. A gap is often the honest
answer, and only someone who knows the platform can say whether a given blank
is a defect or the truth — so the tool quantifies it and leaves the call to a
person.

---

## Accuracy

Both modes are scored against dictionaries built by hand from the same source
files.

| | Rows matched | Field accuracy |
|---|---|---|
| Excel mode | 20/20 | 91.4% |
| SQL views  | 24/24 | 99.3% |

In archive mode the shortfall is entirely files that failed to extract on API
quota — the assembly logic never saw them.

---

## Repo layout

```
src/         9 modules, 
schemas/     5 JSON contracts
.cache/      extraction cache (gitignored; delete to force re-read)
```

---

## Known gaps

- **`lineage.json` is not enforced.** The assembled output has no schema
  validation; it was checked in an earlier version and the check was dropped in
  a rewrite. Worth restoring — about four lines.
- **`merge_field_detail`, `join_diagnostics`, the `ddl_sheet` prompt and
  `ddl_record.json` have no callers.** They were for standalone DDL sheets,
  which the current archive does not usefully provide.
- **The archive layout is assumed, not configured.** Folder names, the cloud
  workbook's filename pattern, and the four stage names are hard-coded. A
  differently-organised archive fails loudly; a *slightly* different one can
  fail quietly.
- **`doc_link` is always null** — nothing supplies an online link.
- **Descriptions are copied, never generated.** Where no source states a
  meaning, the field is null.
