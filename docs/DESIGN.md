# Hecate — design notes

How the program works inside, and why it is built this way. The
[README](../README.md) covers what it does and how to use it; this is for
someone changing the code or reviewing the approach.

---

# How it works

## The pipeline

```
folder → survey → catalog → reader → AI (one file) → checks → assemble → emit
         (free)   (free)    (free)    (PAID)         (free)   (free)    (free)
```

Exactly one step costs money. Everything around it is deterministic and
checkable.

## The two modes

| | Excel archive | SQL scripts |
|---|---|---|
| Lineage lives | across many files | inside one file |
| Stages | 4: source → staging → dwh → cloud | 2: source → view, or source → table |
| Where stages come from | the layout, declared once for the folder | each file's own CREATE statement |
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

### Not every `.sql` file is a view

Each file is classified by the statement it **opens with**, before anything is
read:

| Statement | Kind | Stage the record carries |
|---|---|---|
| `CREATE VIEW` | `view_sql` | `view` |
| `CREATE TABLE ... AS SELECT` | `table_sql` | `table` |
| anything else | — | reported and skipped |

A mixed folder produces **one dictionary**, each record carrying the stage its
own file justified. There is no fallback kind.

This matters more than a label. The completeness check needs an anchor the file
itself states, and for SQL that is the declared column list. A
`CREATE TABLE ... AS SELECT` read as a view has no such list, so the anchor came
back empty and **the completeness check switched itself off in silence** — the
one check that catches a truncated reply — while the file was pooled into every
headline percentage.

Two details in the classifier are load-bearing: **comments are stripped first**
(real scripts open with a `-- DDL for …` banner), and **the match is anchored at
the start** of what remains, so a `CREATE VIEW` inside a comment cannot classify
a file by its documentation.

### Completeness is judged per stage, never against a union

A folder holding both statements yields the stage list `[source, view, table]`,
and no record has all three — so records that are individually complete would
report **0% complete**. Each record is therefore judged only against the stages
its own file declared. Measured on a real 17-file folder: `0/511 (0%)` against
the union, `501/511 (98%)` judged properly.

This is the same trap in reverse from the Excel side, where a stage the layout
*declares* and the folder lacks must still score 0% — that is a real gap and
hiding it would be worse. The difference is who declared the stage: a layout
speaks for the whole archive, a `.sql` file speaks only for itself.

## Configuring a different archive

Folder names, stage names and the final-stage workbook's filename live in a
layout file, not scattered through the code. Drop an `archive.json` beside the
folders (`archive.example.json` is a commented template):

```json
{
  "stages": ["source", "staging", "dwh", "cloud"],
  "hops": [
    {"dir": "SRC_STG", "from": "source",  "to": "staging"},
    {"dir": "STG_DWH", "from": "staging", "to": "dwh"}
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

Don't want to write one by hand? `--survey` proposes one.

## Modules

| Module | Role | AI? |
|---|---|---|
| `kinds.py` | **One definition per source kind.** Imports nothing from the project | no |
| `readers.py` | **One entry per file format.** Picks the best reader installed | no |
| `providers.py` | **One entry per model vendor.** Which AI answers, and how | no |
| `layout.py` | What shape is this archive | no |
| `survey.py` | Reports what is in a folder, and *proposes* a layout | no |
| `catalog.py` | Indexes the archive: `{table → file, sheet, stages}` | no |
| `extract.py` | Sheet → CSV. Classifies SQL statements, finds the completeness anchor | no |
| `agent.py` | **The only AI.** One prompt per source kind | **yes** |
| `store.py` | Converts a file on demand, caches it, isolates failures | no |
| `assemble.py` | Builds lineage: `resolve_table`, `resolve_view`, `chain_views` | no |
| `entities.py` | The assembled shape as types: `Record`, plus `Column`/`Table`/`Lineage` | no |
| `descriptions.py` | Field meanings: export, fill, load back, join | no |
| `rules_doc.py` | Where each attribute comes from, per format | no |
| `validate.py` | Every check and every number | no |
| `emit.py` | Writes the reviewable spreadsheet | no |
| `compare.py` | Scores output against a hand-built reference | no |
| `main.py` | Orchestration only | no |

### The four registries

`kinds.py` says what a document type is, `readers.py` how a file becomes text,
`providers.py` which model answers, and `rules_doc.py` where each attribute is
found. All four work the same way: one frozen dataclass per entry, **no field
with a default**, and a `_check()` that refuses a half-declared entry at import.

Adding a format, a vendor or a document type is **one entry in one file** — and
forgetting half of it stops the program rather than degrading a check in the
middle of a ninety-file run.

`readers.py` and `providers.py` decide by **probing what is installed**. Install
`docling` and PDFs, Word and PowerPoint start working with no code change;
install `litellm` and four more vendors appear. That is what lets one codebase
produce both a small deployment and a full one.

### One definition per concept

Each of these has exactly one home, and in every case the duplicated version
failed *quietly*:

**`kinds.py` — what a source kind is.** A document type used to be declared in
four unrelated dicts keyed by the same bare string. Forgetting one did not
raise — it made the completeness anchor unavailable, which switched the
completeness check off for that kind without saying so.

**`assemble.target_key` — which entry identifies the target field.** Written out
twice, verbatim, and the copies drifted. It deliberately does *not* normalise
like `field_key`: folding case here would merge fields the dictionary reports
separately.

**`assemble.produced_entry` — which entry a record is about.** The end of the
chain, true by construction. It replaced looking the entry up by the stage name
`"view"`, which was correct only while every `.sql` file happened to be a view.

**`entities.py` + `schemas/lineage.json` — the assembled shape.** The schema sat
unreferenced while the code grew four fields it forbade; validating against it
would have rejected 100% of both dictionaries. It is now loaded and enforced on
every run, and `entities.py` refuses to start if the two disagree.

### Functions that carry weight

**`catalog.build_catalog(dir, layout)`** — a file whose *name* matches the table
beats one that merely contains a *sheet* of that name; some workbooks carry a
copy-pasted sheet title from another table, and resolving through those silently
reads the wrong table.

**`extract.expected_row_count`** / **`extract.declared_object`** — the
completeness anchors. A spreadsheet says how many rows it has; a CREATE declares
how many columns. Without these the check is silently skipped, so the report now
names every source that had no anchor and why.

**`extract.classify_sql(text)`** — which statement a `.sql` file opens with,
built from the kind registry. Returns `None` on no match, and `None` means
exactly that: the caller reports it and never falls back to a default.

**`store.RecordStore.records(path, sheet, kind)`** — the whole interface between
assembly and anything expensive. In-memory memo, then disk cache, then extract
and convert. On one real run assembly asked for a file's rows **19 times and it
was read 3 times**. A failed conversion is recorded and returns `[]`: one
transient API error must not destroy a 90-file run.

**`assemble.field_key(table, column)`** — the single definition of "the same
field". Strips and upper-cases **for matching only**; emitted values keep the
source's own spelling and padding.

## Descriptions

Where no source states a meaning, the field's description is `null` — this
program copies descriptions, it does not invent them. A person fills those in,
and their text is kept **beside** the dictionary, never inside it.

`output.json` means exactly one thing: what the documents state, every value
checkable character-for-character against the one file it came from. A sentence
somebody wrote cannot be checked that way. Merging it would leave the
assembled-shape check reporting "N/N records clean" over a dictionary that is
now part testimony, and would turn `with_description` into a permanent 100% —
deleting a real measurement by making it tautological.

So the two are joined at write time, in the spreadsheet a human reads, under
adjacent columns: `Mô Tả` for what a document said, `Mô Tả (bổ sung)` for what
was added, and `Nguồn` naming the document and section when a machine read it
out of a PDF rather than a person writing it.

The unit matters: one record is one (target field, source field) pair, so a
field with ten sources is ten records — but it has **one** meaning. It is
written once and fanned out. Matching is on the normalised key, because Excel is
the round-trip medium and a human retyping a cell reproduces neither the padding
nor the case; a key that matches no field is reported as orphaned and never
discarded.

## The shape has a type, and the type has a schema

`schemas/lineage.json` describes the assembled record exactly, and
`src/entities.py` mirrors it as frozen dataclasses:

```python
from entities import records_from
records = records_from(json.load(open("out/output.json")))
records[0].description                      # the field's business meaning
records[0].lineage[-1].sources[0].role      # not record["lineage"][-1][...]
described = records[0].with_description("Mã địa chỉ")
```

There is also a domain view — `Column`, `Table`, `Lineage` — derived from the
same records, so a description belongs to a `Column` rather than to a row in a
list.

These are a typed **view**, not a new format: `Record.from_dict(d).to_dict() == d`
for every record either mode produces, key order included.

## Checks

| Check | Question | Fatal |
|---|---|---|
| Input | Does the file have data, and a statement this program knows? | yes |
| Shape | Does the agent's reply match the schema? | yes |
| Completeness | distinct target fields == input rows (or declared columns)? | yes |
| Fidelity | Does every table/column name appear verbatim in the source text? | yes |
| Assembled shape | Does the finished dictionary match `lineage.json`? | reported |
| Completeness audit | Which sources could completeness be checked on at all? | no |
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

**Completeness that could not run says so, by name.** Some sources have no
anchor — a `CREATE TABLE x AS SELECT *` declares no column list, and working out
what the star expands to would need another file, which the design forbids.
`report["completeness"]` names each such source and the reason. "Not checked"
and "passed" are not the same shrug.

**An unrecognised `.sql` never reaches a paid API call.** The input check used to
pass anything containing the word "select", which a `GRANT SELECT` does.

The last three are reported and never fail a run. A gap is often the honest
answer, and only someone who knows the platform can say whether a blank is a
defect — so the tool quantifies it and leaves the call to a person.
