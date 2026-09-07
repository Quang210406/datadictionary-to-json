import json
import os

from dotenv import load_dotenv

import kinds
import providers

# Load GEMINI_API_KEY from the .env file into the environment.
load_dotenv()

# Rules that hold for every source type. The fabrication rules are the ones
# validate.py enforces mechanically, so they are kept word for word: if the
# instruction and the check ever drift apart, a failure stops telling us
# which of the two is wrong.
COMMON_RULES = """- One JSON record per data row. Never add, drop, or merge records.
- If a value is unknown or blank, use null for that value.
- Copy values verbatim, as strings — do not reformat, pad, or round them.
- Restructure only. NEVER invent values.
- Output ONLY the JSON array. No markdown, no explanation."""

# One entry per source_kind. Each states what ONE ROW of that file is, which
# is the whole difference between the two: a hop spec row is a mapping
# between two stages, a DDL sheet row is a column definition. Everything
# else about the two prompts is shared.
#
# The bodies live here, beside the AI code, because they are long and because
# this is the only module that sends them anywhere. Which kinds exist is not
# decided here though — kinds.py holds that, and _check_prompts() below
# reconciles the two at import time.
PROMPTS = {
    "hop_spec": {
        "label": "hop specification sheet",
        "heading": "HOP SPECIFICATION",
        "body": """This sheet specifies ONE stage transition of the pipeline (for example
source to staging). One data row = one TARGET field: the target table and
column, the source field(s) it is loaded from, and how it is transformed.

- The rows above the column-header row are sheet-level metadata (source
  system, target table name, load frequency, join/filter conditions). They
  are not data rows: emit no records for them.
- If a data row leaves the target or source table cell blank, use the
  sheet-level Target Table Name / Source Table Name from that metadata block.
- Capture datatype and size at BOTH ends: target_datatype/target_size from
  the target columns, source_datatype/source_size from the source columns.
  They often differ, and both are needed.
- transformation_type is the stated kind of mapping (e.g. "Direct Mapping").
  transformation_logic is the stated expression or rule. These sheets label
  their columns unreliably — the "type" column is usually empty, the "logic"
  column usually holds the type, and the notes column holds the real rule.
  Take each value from wherever it actually sits and copy it as written.

ONE ROW MAY PRODUCE SEVERAL RECORDS. A row is n-1 when it feeds one target
field from more than one source field. That happens two ways:
  (a) the Source Table/Column cell stacks several names on separate lines;
  (b) the cells are blank or partial and the source columns are named only
      inside the transformation/notes prose (e.g. a list of fields checked
      for null, or "check STATUS_CD = 'CP'").
In both cases emit ONE RECORD PER SOURCE FIELD, all sharing the same
target_column, rather than one record with stacked values. Take each source
column name verbatim from the text; if the prose names a table but no column
for it, emit one record for that table with source_column null.

Set source_role for each record:
  "value"     - this field's data becomes the target value (the default)
  "join"      - the table is only joined to locate the row
  "condition" - the field is tested by a rule but its value is not copied
Use null when the text does not make the role clear.""",
    },
    "view_sql": {
        "label": "CREATE VIEW script",
        "heading": "VIEW SOURCE CODE",
        "body": """This file defines ONE database view. A view stores no data of its own — it
is a saved query — so its definition states exactly where each of its columns
comes from. That is the lineage you are extracting.

- The bracket after the view name declares the view's output columns. Those
  names, spelled exactly as declared there, are the target_column values, and
  the declared list is the authoritative set: emit records covering every one
  of them and no others. If the SELECT gives a column a differently-cased
  alias, the DECLARED name still wins.
- The Nth expression in the SELECT list fills the Nth declared column.
- "AS" is optional. `D.LOCATION_FK location_id` aliases just like
  `D.LOCATION_FK AS location_id`.

RESOLVE EVERY NAME TO A REAL TABLE:
- FROM/JOIN clauses give each table a short alias (`CRMDB_UAT.party_addr C`).
  Record the real schema and table, and put the alias in source_alias.
- A `WITH name AS (SELECT ... FROM real_table ...)` block at the top invents a
  name that is NOT a table. Record the real table it selects from, and note
  the WITH block's filter in transformation_logic.

ONE RECORD PER (declared column, source field). A column fed by several
sources produces several records sharing one target_column — a COALESCE of
two lookups gives one record per lookup, a concatenation gives one record per
column concatenated, a CASE gives one record per column it reads.

WHICH SOURCES TO RECORD — this matters:
- Record a source when its value can end up in the column (source_role
  "value"), or when a join inside the value-producing expression is how the
  right row was found (source_role "join"). A correlated subquery like
  (SELECT Name FROM code_lookup WHERE id = C.location_type) gives TWO records:
  code_lookup's real table with role "value", and C.location_type with role
  "join".
- Do NOT emit records for FROM-clause or WHERE-clause joins and filters.
  Those restrict which rows the view returns; they do not supply a column's
  value. Mention them in transformation_logic if they matter.

- transformation_logic is the expression as written: "direct" for a plain
  column reference, otherwise the CASE, COALESCE, concatenation or function
  call copied verbatim.
- When a column's value comes from a function call rather than a column
  (`SOME_TAT(a.id)`), leave source_table and source_column null and put the
  call in transformation_logic. Do not invent a table for it.""",
    },
    "table_sql": {
        "label": "CREATE TABLE ... AS SELECT script",
        "heading": "TABLE SOURCE CODE",
        "body": """This file creates ONE table from a query (CREATE TABLE ... AS SELECT, often
called CTAS). The table stores its result, unlike a view, but for lineage
that difference does not matter: the SELECT states exactly where each column
comes from, and that is what you are extracting.

- If a bracket after the table name declares the output columns, those names,
  spelled exactly as declared there, are the target_column values, and the
  declared list is the authoritative set: emit records covering every one of
  them and no others.
- If there is NO declared bracket, the SELECT list names the columns. Use the
  alias where one is given (`a.PARTY_NO AS customer_id` -> "customer_id"),
  otherwise the column's own name (`a.PARTY_NO` -> "PARTY_NO").
- `SELECT *` names no columns at all. Emit one record per source column you
  can actually see named in the script, and never invent a column name to
  fill the gap — a guessed column is worse than a missing one.
- The Nth expression in the SELECT list fills the Nth declared column.
- "AS" is optional. `D.LOCATION_FK location_id` aliases just like
  `D.LOCATION_FK AS location_id`.

RESOLVE EVERY NAME TO A REAL TABLE:
- FROM/JOIN clauses give each table a short alias (`CRMDB_UAT.party_addr C`).
  Record the real schema and table, and put the alias in source_alias.
- An inline view — a `(SELECT ... FROM real_table) A` in the FROM clause —
  invents a name that is NOT a table. Record the real table it selects from.
- A `WITH name AS (SELECT ... FROM real_table ...)` block does the same.
  Record the real table, and note the block's filter in transformation_logic.

ONE RECORD PER (target column, source field). A column fed by several sources
produces several records sharing one target_column — a COALESCE of two
lookups gives one record per lookup, a concatenation gives one record per
column concatenated, a CASE gives one record per column it reads.

WHICH SOURCES TO RECORD — this matters:
- Record a source when its value can end up in the column (source_role
  "value"), or when a join inside the value-producing expression is how the
  right row was found (source_role "join").
- Do NOT emit records for FROM-clause or WHERE-clause joins and filters.
  Those restrict which rows are loaded; they do not supply a column's value.
  Mention them in transformation_logic if they matter.

- target_table is the table being created, spelled as the CREATE TABLE line
  writes it.
- transformation_logic is the expression as written: "direct" for a plain
  column reference, otherwise the CASE, COALESCE, concatenation or function
  call copied verbatim.
- When a column's value comes from a function call rather than a column,
  leave source_table and source_column null and put the call in
  transformation_logic. Do not invent a table for it.""",
    },
    "doc_prose": {
        "label": "system or database design document",
        "heading": "DOCUMENT TEXT",
        "body": """This is prose — a design document, a specification, a user guide — not a
spreadsheet and not code. It was written for people, so most of it is not
about individual fields at all.

Extract ONLY what the document actually DEFINES about a data field: its
business meaning. One record per (table, column) the text genuinely explains.

- If the document has a data-dictionary or field-listing section — often a
  table with columns like "Tên trường", "Kiểu dữ liệu", "Mô tả" — that is the
  richest source. Take the field name and its description as written.
- A field explained in a sentence counts too ("CUST_STATUS cho biết trạng
  thái hoạt động của khách hàng"). Copy the explanation as the description.
- Prose that merely MENTIONS a field without saying what it means is not a
  definition. Skip it. A screenshot caption, a step in a user guide, or a
  field named in a list of things to fill in is not a description.

- table is the table the field belongs to, when the document says so — a
  section heading, a table caption, or the surrounding text. Use null when
  the document names a field but never says which table it is in. Do NOT
  guess a table from the field's name.
- section is where in the document you found it: the nearest heading, table
  caption, or the page marker ("--- trang 42 ---") if nothing else names the
  place. This is the evidence trail; be specific rather than tidy.
- description is the document's own wording, copied. Do not summarise it, do
  not translate it, do not improve it. If the document is in Vietnamese the
  description stays in Vietnamese.

Emit an empty array if the document defines no fields at all. That is a
truthful answer and a common one — most pages of most documents define
nothing.""",
    },
    "doc_lineage": {
        "label": "system or database design document, read for MAPPINGS",
        "heading": "DOCUMENT TEXT",
        "body": """This is prose — a design document, a specification, a migration plan — not a
spreadsheet and not code. It was written for people, so most of it states no
mapping at all.

Extract ONLY where the document says a field is LOADED FROM another field. One
record per (target field, source field) pair.

- The richest source is a mapping or interface table: two column groups, one
  describing the target and one the source, often captioned "Mapping",
  "Ánh xạ", "Nguồn dữ liệu" or "Interface". Read one record per row.
- A sentence states a mapping too ("CUST_STATUS được lấy từ CIF.STATUS_CD").
  Copy the source it names.
- Prose that merely MENTIONS two tables in one paragraph is NOT a mapping.
  Neither is a list of tables, a screenshot caption, or a data model diagram
  that shows a relationship. A foreign key is not a load.

DO NOT extract what a field MEANS here. A sentence explaining the business
purpose of a column is a description, it is read separately, and a description
copied into transformation_logic would put an explanation where an expression
belongs.

- target_table is the table being loaded, when the document says so — a table
  caption, a section heading, or the surrounding text. Use null when it names a
  field but never says which table it belongs to. Do NOT guess a table from the
  field's name, and do NOT reuse the source table for it.
- ONE ROW MAY PRODUCE SEVERAL RECORDS. A target fed from more than one source
  field gives one record per source field, all sharing the same target_column,
  never one record with stacked values.
- transformation_logic is the stated rule or expression, copied as written
  ("trim", "convert ddmmyy sang YYYYMMDD", a CASE, a concatenation). Use null
  when the document states the mapping but no rule.
- section is where in the document you found it: the nearest heading, table
  caption, or the page marker ("--- trang 42 ---") if nothing else names the
  place. This is the evidence trail; be specific rather than tidy.

Emit an empty array if the document states no mappings at all. That is a
truthful answer and a common one — most pages of most documents map nothing.""",
    },
    "cloud_sheet": {
        "label": "DWH-to-CLOUD reference sheet",
        "heading": "CLOUD REFERENCE SHEET",
        "body": """This sheet describes ONE table as it lands in the cloud. One data row =
ONE COLUMN of that table.

- The rows above the column-header row are a title and a description of the
  table as a whole. They are not data rows: emit no records for them.
- The sheet has two side-by-side column groups, one for the on-premise
  system and one for the cloud ("Loyalty Staging (CLOUD)"). Take table,
  column, datatype, size and nullable from the CLOUD group only.
- description is the business meaning of the field ("Mô tả"), copied as
  written. It is the most valuable column here: copy it in full, including
  Vietnamese text and line breaks. Use null when the cell is empty — never
  invent or summarise a description.""",
    },
}

# The parts of a prompt entry the template below interpolates. Named here so a
# half-written entry is caught at import rather than at the moment of the API
# call, which is both the slowest and the most expensive place to find out.
PROMPT_PARTS = ("label", "heading", "body")


def _check_prompts():
    """Reconcile these prompts with the source kinds registered in kinds.py.

    kinds.py owns which document kinds exist and validates everything else
    about them, but it cannot check this: it deliberately imports nothing from
    the project, so that extract.py can read from it without google-genai
    coming along. The registry therefore checks its own fields, and the module
    that holds the prompts checks that it has one per registered kind.

    Both directions matter. A kind with no prompt fails the run when it is
    reached; a prompt with no kind is dead text that reads as though the kind
    were supported.
    """
    missing = sorted(set(kinds.KINDS) - set(PROMPTS))
    if missing:
        raise ValueError(
            f"source kind(s) {missing} are registered in kinds.py but have no "
            "prompt here; extraction would fail on the first such file.")
    orphaned = sorted(set(PROMPTS) - set(kinds.KINDS))
    if orphaned:
        raise ValueError(
            f"prompt(s) {orphaned} name no registered source kind; add them to "
            "kinds.py or remove them, because nothing can reach them.")
    for name, template in PROMPTS.items():
        absent = [part for part in PROMPT_PARTS if not template.get(part)]
        if absent:
            raise ValueError(
                f"prompt {name!r} is missing {absent}; the prompt would be "
                "built with a hole in it.")


_check_prompts()


# Sends one source file's text to the AI agent, under the prompt for its kind.
def convert(text, schema, source_kind) -> list:
    if source_kind not in PROMPTS:
        raise ValueError(
            f"Unknown source_kind {source_kind!r}; expected one of {sorted(PROMPTS)}"
        )
    template = PROMPTS[source_kind]

    prompt = f"""You are a data restructuring tool. Convert the {template['label']}
below into a JSON array conforming exactly to this JSON Schema:

{json.dumps(schema, indent=2)}

{template['body']}

Rules:
{COMMON_RULES}

{template['heading']}:
{text}"""

    # Which model answers is configuration, not code — see providers.py. The
    # default is still Gemini through its own client, which is the path every
    # published number was measured through.
    return providers.parse_json_array(providers.complete(prompt))
