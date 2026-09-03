# Hecate

Builds a **data dictionary** — every field, where it came from, how it was
transformed, and **which file said so** — out of documentation that was never
designed to be machine-read.

Point it at a folder of spreadsheets, SQL scripts and PDFs. It reads each one,
works out how a field travels from a source system through staging into a
warehouse, and writes the result as JSON you can process and a spreadsheet a
person can review next to the originals.

An AI reads each messy file into flat records; plain Python joins those records
into lineage. Each AI call sees exactly **one** file, so a value can be checked
character-for-character against the file it came from, and a cross-file link
cannot be invented. How that works is in [docs/DESIGN.md](docs/DESIGN.md).

---

## What it does

| | |
|---|---|
| **Reads** | Excel (`.xlsx`), SQL (`CREATE VIEW`, `CREATE TABLE … AS SELECT`), and — with an optional package — PDF, Word, PowerPoint, HTML, including scanned pages via OCR |
| **Builds** | field-level lineage across a multi-stage pipeline, or inside a single SQL file |
| **Explains a folder** | reports what is actually in an unfamiliar folder and *proposes* a layout for it |
| **Models** | `Table`, `Column`, `Lineage` as real types, not loose dictionaries |
| **Collects meanings** | exports a sheet for a person to fill in, reads field meanings out of PDFs, joins both |
| **Documents itself** | generates a table of where each attribute is found, per document format |
| **Checks itself** | six checks per run, including one that proves no value was invented |
| **Runs on any model** | Gemini, OpenAI, Claude, Mistral, or Ollama on your own machine |
| **Scores itself** | compares its output against a dictionary built by hand |

Measured against hand-built dictionaries: **98.4%** field accuracy on an Excel
archive, **99.3%** on SQL views.

---

# Quick start

## 1. What you need

- **Python 3.9 or newer** (3.12 recommended). Check with `python3 --version`.
- **An API key** for one AI provider. A free Google Gemini key takes two
  minutes at [aistudio.google.com](https://aistudio.google.com).
- A folder of documentation to point it at.

## 2. Install

```bash
git clone https://github.com/Quang210406/datadictionary-to-json.git
cd datadictionary-to-json
python3 -m venv .venv
.venv/bin/pip install pandas openpyxl jsonschema python-dotenv google-genai
```

## 3. Give it a key

Create a file called `.env` in the project root:

```
GEMINI_API_KEY=your-key-here
```

## 4. Check it works

```bash
.venv/bin/python tests/test_no_cloud_stage.py
```

Should print `8/8 passed`. This needs **no API key and no network**, so a pass
means the install is sound before you spend anything.

## 5. First real run

```bash
.venv/bin/python src/main.py --archive path/to/your/archive
```

Everything lands in `out/`. The first run is slow because each file is sent to
the model; later runs are near-instant because every extraction is cached by
file **content**.

## 6. Optional — read PDFs and Word documents

```bash
.venv/bin/pip install pypdf      # 0.4 MB — PDF text layer
.venv/bin/pip install docling    # ~1 GB  — adds Word, PowerPoint and OCR
```

Neither is required. Install one and PDFs start working; install `docling` and
it takes over automatically, adding `.docx`, `.pptx`, `.html` and scanned
pages. **No code change and no flag** — the program checks what is installed.

## 7. Optional — use a model other than Gemini

```bash
.venv/bin/pip install litellm
export HECATE_PROVIDER=anthropic        # or openai, mistral, ollama
export ANTHROPIC_API_KEY=your-key
```

`HECATE_MODEL` overrides the model. Without `litellm`, Gemini still works.

---

# Usage

## Build a dictionary from an Excel archive

```bash
python src/main.py --archive path/to/archive
python src/main.py --archive path/to/archive --table DWH_PARTY --table DWH_ACCOUNT
```

Omit `--table` to build every table produced by the last hop. Each table costs
API calls, so start with one or two.

## Build from SQL scripts

```bash
python src/main.py --sql path/to/sql/folder
```

Quote the path if it contains spaces. Each `.sql` file is classified by the
statement it opens with; anything unrecognised is reported and skipped without
costing a call.

## Point it at a folder it does not recognise

```bash
python src/main.py --survey path/to/folder --survey-out archive.json
python src/main.py --archive path/to/folder --layout archive.json
```

The survey **reports facts** — which subfolders, how many workbooks, which
table each describes — and then **proposes** a layout with the evidence for
each part. It never applies one: a wrong stage *order* passes every check this
program has and produces a confidently wrong pipeline. Read the proposal,
especially the order, before using it.

Costs nothing: it reads folder and sheet **names**, never a cell.

You can also write the layout by hand — `archive.example.json` is a commented
template. Resolution order is `--layout FILE` → `archive.json` inside the
archive → a built-in default.

## Fill in field meanings

The program only ever **copies** a description when a document states one.
Where nothing states a meaning, the field is blank — that is the gap a person
fills.

```bash
# 1. export one row per distinct field
python src/main.py --archive DIR --describe-template mo_ta.xlsx

# 2. open mo_ta.xlsx, fill the "Mô Tả (bổ sung)" column, save

# 3. read it back in
python src/main.py --archive DIR --descriptions mo_ta.xlsx
```

One description per **field**, not per record — a field fed by ten sources is
ten rows in the output but has one meaning, and it fans out automatically.
Matching is by table and column, so you can sort and filter the sheet freely,
and case or stray spaces will not break it. A row matching no field is reported
as orphaned and kept, never silently dropped.

Your text is **never written into `output.json`**, which holds only what the
source documents state. It is joined into the spreadsheet instead.

## Read meanings out of PDFs

```bash
python src/main.py --archive DIR --from-docs path/to/documents \
                   --describe-template mo_ta.xlsx
```

Reads each prose document on its own, extracts what it says a field **means**,
matches those meanings to fields this dictionary actually has, and pre-fills the
template. Every pre-filled row names the document **and the section** it came
from, so a reviewer can tell a machine-read meaning from a hand-written one.

Meanings for fields this run did not build are reported, not dropped — a design
document describes the whole system, and most of it is about other tables.

## Document where each attribute comes from

```bash
python src/main.py --rules-doc rules.xlsx
```

Writes a table of **entity | attribute | format | insight type | where it is
found** — "the sheet name, never the row cell", "the declared column list in
the bracket after the view name". Needs no archive and no API call: it
describes the formats, not a run.

## Score against a hand-built reference

```bash
python src/compare.py ground_truth.xlsx out/output.json          # Excel mode
python src/compare.py ground_truth.xlsx out/views.json --views   # SQL mode
```

Turns "does it work?" into a number per column. Writes `out/compare.json`,
overwriting the previous comparison — read one before running the other.

## Every option

| Flag | What it does |
|---|---|
| `--archive DIR` | build from an Excel archive |
| `--sql DIR_OR_FILE` | build from SQL scripts |
| `--table NAME` | which table to build; repeatable; omit for all |
| `--layout FILE` | describe a differently-shaped archive |
| `--survey DIR` | report a folder's contents and propose a layout |
| `--survey-out FILE` | save that proposal |
| `--describe-template FILE` | export the field-description sheet |
| `--descriptions FILE` | read a filled-in sheet back |
| `--from-docs DIR_OR_FILE` | read field meanings out of prose documents |
| `--rules-doc FILE` | write the extraction-rules table |
| `--out` / `--xlsx` / `--report` | override output paths |
| `--cache FILE` | the extraction cache; delete it to force re-reading |

Output paths default per mode — `out/output.*` for an archive, `out/views.*`
for SQL, each with its own cache. **Neither command needs an output flag**, and
neither mode can overwrite the other's files.

---

## What comes out

Three files per run, in `out/`:

| File | What it is |
|---|---|
| `output.json` | the dictionary, for machines |
| `output.xlsx` | the same records laid out for review by eye |
| `report.json` | per-file validation, coverage, chain diagnostics, failures |

**One record is one (target field, source field) pair** — not one target field.
That is what lets a field with ten sources exist as ten records sharing a
target, instead of ten values stuffed into one cell.

```json
{ "description": "business meaning, when a source states one",
  "lineage": [
    { "stage": "staging", "table": "STG_PARTY", "column": "OPEN_DT",
      "datatype": "DATE", "size": "8",
      "offline_path": "which file said so",
      "sources": [] },
    { "stage": "dwh", "table": "DWH_PARTY", "column": "OPEN_DT",
      "datatype": "DATE", "size": "8",
      "offline_path": "which file said so",
      "sources": [ { "table": "STG_PARTY", "column": "OPEN_DT",
                     "transformation_logic": "the rule as written",
                     "role": "value" } ] }
  ] }
```

`offline_path` on each entry is the evidence trail. `sources` hangs off the
stage that was *produced*; the origin stage has an empty list. `role`
distinguishes a value source from a table joined only to locate the row.

To work with the output as types rather than dictionaries:

```python
from entities import records_from
records = records_from(json.load(open("out/output.json")))
records[0].description
records[0].lineage[-1].sources[0].role
```



## Limitations

- **Descriptions are copied, never generated.** Where no source states a
  meaning the field is `null`. Fill it by hand or from a document.
- **A `CREATE TABLE … AS SELECT *` cannot be completeness-checked.** It declares
  no column list, and deriving one would need a second file. Reported
  explicitly rather than skipped.
- **OCR on scanned pages drops Vietnamese diacritics.** Text comes out
  readable, but identifiers from a scan are low-confidence.
- **A layout is still required** for an archive. The survey proposes one, but
  nothing is inferred silently.
- **Gaps are counted, never judged.** A blank is often the truthful answer, and
  only someone who knows the platform can say whether it is a defect.

---

Design and internals: [docs/DESIGN.md](docs/DESIGN.md)
