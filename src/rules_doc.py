"""Where each entity attribute comes from, per document format.

The deliverable this feeds is a sentence of the form:

    Đối với thực thể [Column]: với văn bản định dạng [Excel / hop spec],
    [datatype] có thể trích xuất từ [cột "Target Datatype", ở các dòng bên
    dưới dòng tiêu đề]

That is an extraction-rules document — a table saying, per entity attribute
and per document format, WHERE in the document the value is found. This module
emits a first draft of it, so the job starts as a review rather than a blank
page, and every row a reviewer corrects is a real finding about the extractor.

**Where the content actually comes from.** Two halves, and they are kept apart
on purpose:

  * The SKELETON is derived. Which kinds exist, which reader each uses, which
    statement it matches and which header anchors locate its header row all
    come from `kinds.py`; which attributes each kind produces comes from that
    kind's JSON schema. Nothing here restates any of it.
  * The PROSE is authored, once, in WHERE below. A sentence like "the sheet
    name, never the row cell" is knowledge that lives in the prompt bodies and
    in hard-won comments, and no parser can lift it out of English reliably.

Because the prose is authored it can drift from the registry, which is the
exact failure this codebase keeps being bitten by. So `_check()` runs at import
and refuses a WHERE that does not cover every attribute of every registered
kind. Add a source kind or a schema field and this module stops the program
until somebody writes down where the new thing comes from.

The `insight` column uses the taxonomy from the article the work was briefed
against: document structure, table data, key-value pair, derived insight.
"""

import json
from pathlib import Path

import kinds

# The four kinds of extractable insight, in the vocabulary of the brief.
STRUCTURE = "document structure"
TABLE_DATA = "table data"
KEY_VALUE = "key-value pair"
DERIVED = "derived insight"

# Human names for the formats, since "hop_spec" means nothing to a reader who
# has not read the code.
FORMATS = {
    "doc_prose": "PDF / Word — prose design document, read for meanings",
    "doc_lineage": "PDF / Word — prose design document, read for mappings",
    "hop_spec": "Excel — hop specification sheet",
    "cloud_sheet": "Excel — cloud reference sheet",
    "view_sql": "SQL — CREATE VIEW script",
    "table_sql": "SQL — CREATE TABLE ... AS SELECT script",
}

# (entity, attribute, insight type, where it is found).
#
# One entry per (kind, schema field). The "where" is deliberately structural —
# naming the part of the document, not just the file — because that is what the
# deliverable asks for and what a reader can go and check.
WHERE = {
    "hop_spec": {
        "target_table": (
            "Table", "name", STRUCTURE,
            "The SHEET NAME. Not the 'Target Table Name' row cell, which "
            "frequently holds the SOURCE table copied down the column; "
            "resolution reaches each file by name lookup and reads only its "
            "source side, so that cell is never consulted."),
        "target_column": (
            "Column", "name", TABLE_DATA,
            "The 'Target Column' column, in rows BELOW the column-header row. "
            "The header row is found by anchor words, because the captions "
            "vary by author; everything above it is sheet-level metadata."),
        "target_datatype": (
            "Column", "datatype", TABLE_DATA,
            "The 'Target Datatype' column of the same row."),
        "target_size": (
            "Column", "size", TABLE_DATA,
            "The 'Target Size'/'Length' column of the same row."),
        "source_table": (
            "Lineage", "origin table", TABLE_DATA,
            "The 'Source Table' column. May be blank, in which case the "
            "sheet-level Source Table Name from the metadata block applies; "
            "may also stack several tables in one cell, which is n→1."),
        "source_column": (
            "Lineage", "origin column", TABLE_DATA,
            "The 'Source Column' column, or named only inside the "
            "transformation/notes prose when the cell is blank."),
        "source_datatype": (
            "Lineage", "origin datatype", TABLE_DATA,
            "The source-side datatype column. Differs from the target in "
            "about 10% of rows, which is why both ends are captured."),
        "source_size": (
            "Lineage", "origin size", TABLE_DATA,
            "The source-side size column."),
        "transformation_type": (
            "Lineage", "transformation type", TABLE_DATA,
            "Nominally the 'Transformation Type' column — but these sheets "
            "label unreliably: that column is usually empty, the 'logic' "
            "column usually holds the type, and the notes column holds the "
            "real rule. Take each value from wherever it actually sits."),
        "transformation_logic": (
            "Lineage", "transformation rule", TABLE_DATA,
            "The stated expression or rule, wherever it sits — often the "
            "notes column rather than the one headed 'logic'."),
        "source_role": (
            "Lineage", "source role", DERIVED,
            "Not stated as a column. Inferred from the prose: a field whose "
            "value is copied is 'value', a table joined only to locate the "
            "row is 'join', a field tested by a rule but not copied is "
            "'condition'."),
    },
    "cloud_sheet": {
        "table": (
            "Table", "name", STRUCTURE,
            "The sheet name, one sheet per table. The cloud workbook files "
            "some tables without the warehouse prefix, which is why lookup "
            "tries each configured prefix stripped."),
        "column": (
            "Column", "name", TABLE_DATA,
            "The 'Column'/'Trường'/'Cột' column, in rows below the header."),
        "datatype": ("Column", "datatype", TABLE_DATA,
                     "The cloud-side datatype column."),
        "size": ("Column", "size", TABLE_DATA,
                 "The cloud-side length column."),
        "nullable": ("Column", "constraint", TABLE_DATA,
                     "The 'Nullable' column."),
        "description": (
            "Column", "description", KEY_VALUE,
            "The 'Mô tả' column — the ONLY place in the whole archive that "
            "states a field's business meaning. This is why 59 of 70 fields "
            "arrive described and the rest arrive blank."),
    },
    "doc_lineage": {
        "target_table": (
            "Table", "name", STRUCTURE,
            "The caption of the mapping table, the section heading above it, or "
            "the surrounding sentence. A document has no sheet name to fall "
            "back on, so unlike a hop spec this really is read from the text — "
            "which is why a claim built from it is marked subject_trusted=False "
            "and counted separately in the report. Null where the document "
            "names a field but never its table; never guessed from the field."),
        "target_column": (
            "Column", "name", TABLE_DATA,
            "The target-side column of a mapping table row, or the field named "
            "as being loaded in a sentence. This is the join key and the one "
            "value that may not be null."),
        "source_table": (
            "Lineage", "source table", TABLE_DATA,
            "The source-side table of the same row, or the table named as the "
            "origin in the sentence. Null when the document states a source "
            "column without saying which table holds it."),
        "source_column": (
            "Lineage", "source column", TABLE_DATA,
            "The source-side column of the same row. n-1 is expressed as "
            "several records sharing one target_column, one per source field."),
        "transformation_logic": (
            "Lineage", "transformation", DERIVED,
            "The stated rule or expression, copied as written — a trim, a date "
            "conversion, a CASE. Null when the document states the mapping but "
            "no rule. Never a description of what the field MEANS: that is a "
            "different claim, read under doc_prose, and putting it here would "
            "file an explanation where an expression belongs."),
        "section": (
            "Lineage", "evidence", STRUCTURE,
            "Where in the document the mapping was found: the nearest heading, "
            "the table caption, or the page marker the reader inserts "
            "(\"--- trang N ---\") when nothing else names the place. It is "
            "what makes a prose claim checkable at all — a 138-page PDF cited "
            "as a whole is not evidence a reviewer can act on."),
    },
    "doc_prose": {
        "table": (
            "Table", "name", STRUCTURE,
            "The section heading or table caption that introduces the field "
            "list — a design document groups fields under the table they "
            "belong to rather than repeating the table on every row. Null "
            "when the document names a field but never says which table it "
            "is in; the table is NOT guessed from the field's name."),
        "column": (
            "Column", "name", TABLE_DATA,
            "The field-name column of a data-dictionary table (\"Tên trường\", "
            "\"Field\"), or the field named in a sentence that defines it. A "
            "field merely mentioned in a user guide or a screenshot caption is "
            "not a definition and is not extracted."),
        "description": (
            "Column", "description", TABLE_DATA,
            "The \"Mô tả\" column of that same data-dictionary table, or the "
            "explaining clause of the defining sentence. Copied as written, "
            "in the document's own language. This is the ONLY source of field "
            "meanings outside the cloud workbook, which is why a design "
            "document is worth reading at all."),
        "section": (
            "Lineage", "evidence section", STRUCTURE,
            "Where in the document the definition was found: the nearest "
            "heading, the table caption, or the page marker. This is the "
            "\"which part of the document\" that a file path alone cannot "
            "give — the provenance is the section, not just the file."),
    },
    "view_sql": {
        "target_table": (
            "Table", "name", STRUCTURE,
            "The name after CREATE ... VIEW, quoted when it contains spaces."),
        "target_column": (
            "Column", "name", STRUCTURE,
            "The DECLARED COLUMN LIST — the bracket between the view name and "
            "AS. That list is authoritative: if the SELECT gives a "
            "differently-cased alias, the declared name still wins. It is "
            "also the completeness anchor, the count a truncated reply is "
            "caught against."),
        "source_schema": ("Lineage", "origin schema", STRUCTURE,
                          "The schema qualifier in the FROM/JOIN clause."),
        "source_table": (
            "Lineage", "origin table", STRUCTURE,
            "The real table in the FROM/JOIN clause. A WITH block or an "
            "inline view invents a name that is NOT a table; the real one it "
            "selects from is what gets recorded."),
        "source_column": (
            "Lineage", "origin column", STRUCTURE,
            "The Nth expression of the SELECT list fills the Nth declared "
            "column."),
        "source_alias": ("Lineage", "origin alias", STRUCTURE,
                         "The short alias bound in the FROM/JOIN clause."),
        "source_role": (
            "Lineage", "source role", DERIVED,
            "Inferred from position: a value-producing expression gives "
            "'value', a join inside that expression gives 'join'. FROM- and "
            "WHERE-clause joins are NOT recorded — they restrict which rows "
            "the view returns, they do not supply a column's value."),
        "transformation_logic": (
            "Lineage", "transformation rule", STRUCTURE,
            "The expression as written: 'direct' for a plain column "
            "reference, otherwise the CASE, COALESCE, concatenation or "
            "function call copied verbatim."),
    },
}
# A CTAS states the same facts a view does, and shares its schema, so it shares
# its rules — with one difference worth stating, handled in _rows() below.
WHERE["table_sql"] = dict(WHERE["view_sql"])

TABLE_SQL_OVERRIDES = {
    "target_table": (
        "Table", "name", STRUCTURE,
        "The name after CREATE TABLE."),
    "target_column": (
        "Column", "name", STRUCTURE,
        "The declared column list IF the statement has one. A "
        "`CREATE TABLE x AS SELECT *` declares none, and then the SELECT list "
        "names the columns — or, under a star, nothing does. That is why "
        "completeness reports 'not checked' for such a file rather than "
        "passing it: working out what the star expands to would need a second "
        "file, which the design forbids."),
}
WHERE["table_sql"].update(TABLE_SQL_OVERRIDES)

COLUMNS = ["Thực thể", "Thuộc tính", "Định dạng văn bản", "Loại insight",
           "Trích xuất từ", "Trường trong bản trích xuất"]


def _schema_fields(kind_name, schema_dir):
    path = Path(schema_dir) / kinds.get(kind_name).schema_file
    schema = json.loads(path.read_text(encoding="utf-8"))
    return list(schema["items"]["properties"])


def _check(schema_dir):
    """Refuse to emit a draft that does not cover the registry.

    The skeleton is derived and the prose is authored, so the two can drift.
    Every other place in this project where that was possible, it happened —
    and it happened silently. Here it stops the run instead.
    """
    for name in kinds.KINDS:
        if name not in WHERE:
            raise ValueError(
                f"source kind {name!r} is registered but rules_doc says "
                "nothing about where its attributes come from.")
        declared = set(_schema_fields(name, schema_dir))
        described = set(WHERE[name])
        missing = sorted(declared - described)
        extra = sorted(described - declared)
        if missing or extra:
            raise ValueError(
                f"rules_doc and {kinds.get(name).schema_file} disagree for "
                f"{name!r}: "
                + (f"no rule written for {missing}; " if missing else "")
                + (f"rules written for {extra}, which the schema does not "
                   "produce; " if extra else "")
                + "a draft with a hole in it is worse than no draft.")
    for name in sorted(set(WHERE) - set(kinds.KINDS)):
        raise ValueError(
            f"rules_doc describes {name!r}, which is not a registered source "
            "kind; it would be read as though the format were supported.")


def rows(schema_dir, only=None) -> list:
    """The draft table, one row per (kind, attribute)."""
    _check(schema_dir)
    wanted = list(only) if only else list(kinds.KINDS)
    out = []
    for name in wanted:
        for field in _schema_fields(name, schema_dir):
            entity, attribute, insight, where = WHERE[name][field]
            out.append([entity, attribute, FORMATS.get(name, name), insight,
                        where, field])
    out.sort(key=lambda r: (r[0], r[2], r[1]))
    return out


def write(schema_dir, path, only=None):
    """Emit it as a spreadsheet, since the reader works in Excel."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    table = rows(schema_dir, only)
    wb = Workbook()
    ws = wb.active
    ws.title = "Rules"
    for i, header in enumerate(COLUMNS, start=1):
        cell = ws.cell(1, i, header)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="EEEEEE")
    for r, row in enumerate(table, start=2):
        for c, value in enumerate(row, start=1):
            cell = ws.cell(r, c, value)
            cell.alignment = Alignment(vertical="top", wrap_text=c == 5)
            cell.number_format = "@"
    for c, width in {1: 12, 2: 22, 3: 34, 4: 20, 5: 88, 6: 22}.items():
        ws.column_dimensions[get_column_letter(c)].width = width
    ws.freeze_panes = "A2"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path, len(table)
