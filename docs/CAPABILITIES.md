# What Hecate does, what it does not, and what it checks

A plain account for explaining the program to someone who has not read the
code. Three sections: what it can do, what it deliberately cannot, and what
each check actually verifies.

---

## 1. What it does

It turns documentation that was never meant to be machine-read into a **data
dictionary**: every field, where it came from, how it was transformed, and
**which file said so**.

### The one rule everything follows from

> **AI reads files. Python joins them.**

Each AI call sees exactly **one** file. Every relationship *between* files is
computed deterministically in code.

This is not a style preference. It buys two properties that nothing else in the
design could provide:

1. **Every value is checkable.** An identifier in the output can be found
   character-for-character in the single file it came from.
2. **A cross-file link cannot be invented.** The model was never shown two
   files at once, so it had no opportunity to relate them incorrectly. The
   relationships are arithmetic, not opinion.

A consequence worth stating: when a result is wrong, you can tell whether
*extraction* or *assembly* caused it. Never both.

### The pipeline

```
folder → survey → catalog → reader → AI (one file) → checks → assemble → emit
         free      free       free     PAID           free     free      free
```

Exactly one step costs money. Everything around it is deterministic, free, and
repeatable.

### Capabilities, one by one

| Capability | What it means in practice |
|---|---|
| **Reads many formats** | Excel, SQL (`CREATE VIEW`, `CREATE TABLE … AS SELECT`), and — with an optional package — PDF, Word, PowerPoint, HTML, including scanned pages via OCR |
| **Builds lineage** | traces a field backwards across ~90 workbooks, or reads it out of a single SQL file |
| **Explains an unfamiliar folder** | reports what is actually there, then *proposes* a layout with the evidence for each part |
| **Models the domain** | `Table`, `Column`, `Lineage` as real types, reconciled against a schema on every run |
| **Collects field meanings** | exports a sheet a person fills in; also reads meanings out of PDFs and pre-fills it |
| **Documents its own rules** | generates a table of where each attribute is found, per document format |
| **Runs on any model** | Gemini, OpenAI, Claude, Mistral, or Ollama locally |
| **Scores itself** | compares its output against a dictionary built by hand |
| **Caches by content** | re-runs are free; a cache is portable to another machine |

### Two things that are less obvious and more important

**A `.sql` file is classified by the statement it opens with**, after comments
are stripped, anchored at the start. Not by its extension, not by a default. A
file matching nothing is reported and skipped and never reaches a paid call.
This mattered: a `CREATE TABLE … AS SELECT` sitting in a folder of views was
read as a view end to end, and because a view's completeness anchor is its
declared column list — which a CTAS has none of — **the completeness check
switched itself off in silence** while the file was counted in every headline
percentage.

**Completeness is judged per stage, never against a union.** A folder holding
both statement kinds yields the stage list `[source, view, table]` and no
record has all three, so records that are individually complete would report
0%. Measured on a real 17-file folder: `0/511 (0%)` against the union,
`501/511 (98%)` judged properly.

### Two registries decide by what is installed

`readers.py` and `providers.py` probe rather than assume. Install `docling` and
PDFs, Word and PowerPoint start working — **no code change, no flag**. Install
`litellm` and four more model vendors become selectable.

This is what lets one codebase produce a small deployment for someone who only
needs spreadsheets and a full one for someone who needs OCR. The difference is
which packages are present, not which version of the program they have.

---

## 2. What it does not do

These are decisions, not omissions. Each one is a case where doing the thing
would have made the output less trustworthy.

### It does not generate descriptions

Where no source document states a field's meaning, the description is `null`.
The program **copies** meanings; it never invents one.

This is the largest gap against the original requirement, and it is deliberate.
A generated description would be indistinguishable from a copied one in the
output, and only the copied one can be checked against a file. A person writes
those, or a design document supplies them — and when a document supplies one,
the sheet names the document and the section, so the two never blur.

### It does not infer a layout

The survey **reports** what is in a folder and **proposes** a layout. It never
applies one.

The reason is specific: a wrong stage **order** passes fidelity (every value
still appears in its source file), passes completeness (every row still
produced a record), and emits a confidently wrong pipeline. No single file can
verify an order, so it would be the first claim in the system that nothing can
check. Reporting cannot cause that; inferring silently can.

### It does not check completeness it cannot honestly check

A `CREATE TABLE x AS SELECT *` declares no column list. Working out what the
star expands to would require reading a second file, which the governing rule
forbids. So the report says **"not checked"** and names the file — rather than
passing it and letting a truncated reply through unnoticed.

"Not checked" and "passed" are different states, and the report keeps them
different.

### It does not judge gaps

Coverage numbers and chain diagnostics are **counted, never adjudicated**. A
blank is often the truthful answer — the source document simply does not say —
and only someone who knows the platform can tell a genuine gap from a defect.
The program quantifies and leaves the call to a person.

### It does not put authored text into the dictionary

`output.json` means exactly one thing: what the documents state. A sentence a
person wrote cannot be checked character-for-character against a source, so
merging it would leave the shape check reporting "N/N records clean" over a
dictionary that is now part testimony, and would turn the `with_description`
metric into a permanent 100% — deleting a real measurement by making it
tautological.

Authored text lives beside the dictionary and is joined into the spreadsheet,
where a human reads it.

### Practical limits

| Limit | Detail |
|---|---|
| Scanned PDFs | OCR works but drops Vietnamese diacritics, so identifiers from a scan are low-confidence |
| SQL spreadsheet | has no description column yet; the Excel one does |
| A layout is required | the survey proposes one, but something must confirm it |
| API quota | 429 and 503 are routine; a failed file is recorded, the run continues, and re-running retries only what failed |
| One AI call per file | deliberately not batched, which is slower and is the price of the guarantee |

---

## 3. What the checks check

Six checks per run, at four points. **Four are fatal** — they mark a file's
extraction as failed. **Two are reported** — they inform without judging.

### Checkpoint 1 — before spending anything

Runs **before** the API call, so a bad input costs nothing.

| Source | What is verified |
|---|---|
| Spreadsheet | has data rows, and at least 3 columns — a mapping table cannot have fewer |
| SQL | opens with a statement the registry knows, **and** that statement is the one the caller thinks it is |
| Document | the reader returned enough text to be a document rather than a scan |

The SQL check used to pass anything containing the word "select" — which a
`GRANT SELECT` does. It now requires a recognised `CREATE`, so an unrecognised
file **never reaches a paid call**.

### Checkpoint 2 — the reply, three ways

**Shape.** Does the reply match the JSON Schema for this source kind? Generated
from a Pydantic model (`src/templates.py`), so the contract is declared once.
Catches wrong types, missing keys and invented keys.

**Completeness.** Did every input row produce a record?

The subtlety: **it counts distinct target fields, not records.** One input row
can legitimately produce several records under n→1 — a field fed by three
sources is three records. Counting records would flag correct output as wrong.
The report gives `fields_covered` and `records_emitted` separately, because a
metric that is not the thing being checked trains people to ignore the report.

The anchor differs by format: a spreadsheet states its row count, a `CREATE`
states its declared column list. Where neither exists, the check does not run
and says so.

**Fidelity — the strongest guarantee.** Every table and column name in the
reply is searched for **character-for-character** in the text the agent was
given. A value that is not there is flagged as a possible fabrication.

Because each call saw exactly one file, this is a genuine proof rather than a
heuristic. Nulls are counted but not judged — a null may be a faithful gap.

### Checkpoint 3 — the finished dictionary

**Assembled shape.** Does the whole assembled dictionary match
`schemas/lineage.json`? This checks the thing *Python* built, as opposed to
what the AI returned.

It is reported rather than fatal, but for a different reason than coverage is:
a violation here is never truthful — it means the assembler produced something
malformed. It does not abort only because aborting after every file has been
read would destroy work that may have cost API calls.

Worth knowing: this schema was **defined and never loaded** for months. By the
time it was wired up the records had grown four fields it forbade, and
validating against it would have rejected 100% of both dictionaries. Nothing
noticed, because nothing asked. It is now enforced on every run, and the type
layer refuses to start if the two disagree.

### Checkpoint 4 — reported, never fatal

**Coverage** — how much got filled, per stage: how many records reached each
stage, how many carry a datatype, a description, a transformation rule, how
many target fields are n→1.

**Chain diagnostics** — where a chain started or stopped early, naming both
ends of every break. A hop record joins to the chain before it on (table,
column); when that join fails nothing raises, it just yields two short chains
where one long one was expected — invisible in a record count. The two
spellings side by side are the diagnosis.

**Completeness audit** — which sources completeness could be checked on at
all, and the reason for each that could not.

These never fail a run, because a gap is often the honest answer.

### What the checks cost

All of them are pure Python over data already in memory. Only the extraction is
paid, and **verdicts are never cached** — only extractions are. So changing a
check takes effect immediately on the next run, without re-paying for anything.

---

## 4. The numbers

Scored against dictionaries a person built **by hand** from the same source
files — not against the program's own output.

| | Rows matched | Field accuracy |
|---|---|---|
| Excel archive | 20/20 | **366/372 — 98.4%** |
| SQL views | 24/24 | **143/144 — 99.3%** |

All 16 views extracted with **2492/2492 fidelity**. Both dictionaries validate
against `schemas/lineage.json` with **0 violations**.

Six test suites, none of which need an API key, a network or a quota — only the
single AI step is stubbed, and everything downstream is the real code:

```
test_no_cloud_stage.py    8/8    what a declared-but-missing stage does
test_sql_kinds.py        30/30   mixed statements in one folder
test_entities.py         16/16   the typed view and its schema
test_descriptions.py     17/17   the description round-trip
test_survey.py           16/16   surveying an unknown folder
test_templates.py        11/11   the Pydantic contract is unchanged
```

`test_sql_kinds.py` counts the stubbed agent's calls, because half of what it
asserts is **which files never reach it**.
