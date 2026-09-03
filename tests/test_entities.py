"""The typed entities are a VIEW over the records, not a new format.

    python tests/test_entities.py

No API key, no network, no stubs — nothing here is AI-shaped. Two claims are
under test, and both are the kind that only fail quietly:

  1. Round-tripping a record through the types returns the SAME JSON, byte for
     byte. If it does not, adopting the types anywhere would silently rewrite
     a published dictionary — and the give-away would be a diff in a file
     nobody diffs.

  2. src/entities.py and schemas/lineage.json describe the same shape. That
     schema sat unreferenced while the code grew four fields it forbade
     (`schema`, `role`, `alias`, `resolved_source`); validating against it
     would have rejected every record in both dictionaries. A schema nothing
     loads does not stay true, so the agreement is checked rather than
     assumed.

The two source shapes are the subtle part. An archive source has no `schema`
and no `alias` KEY AT ALL — a hop spec has no such concept — while a SQL
source has both, null when the statement is silent. ABSENT and None are
different on purpose, and collapsing them would add null keys to 83 published
archive records.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import jsonschema

import entities
from entities import ABSENT, Record, Source, StageEntry

SCHEMA = json.loads((ROOT / "schemas" / "lineage.json").read_text(encoding="utf-8"))

# --- records in exactly the shape assemble.py writes -----------------------

ARCHIVE_RECORD = {
    "description": "Ngày mở tài khoản",
    "lineage": [
        {"stage": "source", "schema": None, "table": "RAW_PARTY",
         "column": "OPEN_DT", "datatype": "DATE", "size": "8",
         "constraint": None, "doc_link": None,
         "offline_path": "/a/SRC_STG/STG_PARTY.xlsx", "sources": []},
        {"stage": "dwh", "schema": None, "table": "DWH_PARTY",
         "column": "OPEN_DT", "datatype": "DATE", "size": "8",
         "constraint": None, "doc_link": None,
         "offline_path": "/a/STG_DWH/DWH_PARTY.xlsx",
         "sources": [{"table": "STG_PARTY", "column": "OPEN_DT",
                      "transformation_type": "Direct Mapping",
                      "transformation_logic": "1-1", "role": "value"}]},
    ],
}

VIEW_RECORD = {
    "description": None,
    "lineage": [
        {"stage": "source", "schema": "CRMDB_UAT", "table": "party_addr",
         "column": "LOCATION_FK", "datatype": None, "size": None,
         "constraint": None, "doc_link": None,
         "offline_path": "/a/PARTY_CONTACT_NO.sql", "sources": []},
        {"stage": "view", "schema": None, "table": "PARTY_CONTACT_NO",
         "column": "LOCATION_ID", "datatype": None, "size": None,
         "constraint": None, "doc_link": None,
         "offline_path": "/a/PARTY_CONTACT_NO.sql",
         "sources": [{"schema": "CRMDB_UAT", "table": "party_addr",
                      "column": "LOCATION_FK", "alias": "D",
                      "transformation_type": None,
                      "transformation_logic": "direct", "role": "value"}]},
    ],
}

CHAINED_RECORD = dict(
    VIEW_RECORD,
    resolved_source={"schema": None, "table": "CUST", "column": "PARTY_NO",
                     "via": ["PARTY_CONTACT_NO.LOCATION_ID"]})

ALL = [ARCHIVE_RECORD, VIEW_RECORD, CHAINED_RECORD]


def reconcile_rejects(mutate):
    """True if reconcile_with_schema refuses a schema `mutate` has damaged."""
    schema = json.loads(json.dumps(SCHEMA))     # deep copy
    mutate(schema)
    try:
        entities.reconcile_with_schema(schema)
        return False
    except ValueError:
        return True


def main_():
    print("=" * 74)
    print("ROUND TRIP")
    print("=" * 74)
    for label, record in (("archive", ARCHIVE_RECORD), ("view", VIEW_RECORD),
                          ("chained view", CHAINED_RECORD)):
        back = Record.from_dict(record).to_dict()
        same = json.dumps(back, ensure_ascii=False) == json.dumps(record, ensure_ascii=False)
        src = back["lineage"][-1]["sources"][0]
        print(f"  {label:<14} byte-identical: {str(same):<5}  "
              f"source keys: {list(src)}")

    print()
    print("=" * 74)
    print("THE ABSENT / None DISTINCTION")
    print("=" * 74)
    archive_src = Source.from_dict(ARCHIVE_RECORD["lineage"][1]["sources"][0])
    view_src = Source.from_dict(VIEW_RECORD["lineage"][1]["sources"][0])
    print(f"  archive source .schema : {archive_src.schema!r}  "
          f"-> key emitted: {'schema' in archive_src.to_dict()}")
    print(f"  view    source .schema : {view_src.schema!r}  "
          f"-> key emitted: {'schema' in view_src.to_dict()}")

    validator = jsonschema.Draft202012Validator(SCHEMA)
    violations = list(validator.iter_errors(ALL))

    described = Record.from_dict(VIEW_RECORD).with_description("Mã địa chỉ")
    original = Record.from_dict(VIEW_RECORD)

    checks = [
        # 1. the types do not rewrite the data
        ("an archive record round-trips byte for byte",
         json.dumps(Record.from_dict(ARCHIVE_RECORD).to_dict(), ensure_ascii=False)
         == json.dumps(ARCHIVE_RECORD, ensure_ascii=False)),
        ("a view record round-trips byte for byte",
         json.dumps(Record.from_dict(VIEW_RECORD).to_dict(), ensure_ascii=False)
         == json.dumps(VIEW_RECORD, ensure_ascii=False)),
        ("a chained record keeps resolved_source",
         json.dumps(Record.from_dict(CHAINED_RECORD).to_dict(), ensure_ascii=False)
         == json.dumps(CHAINED_RECORD, ensure_ascii=False)),
        ("a record with no resolved_source does not grow one",
         "resolved_source" not in Record.from_dict(VIEW_RECORD).to_dict()),
        ("an archive source gains no schema/alias keys",
         set(archive_src.to_dict())
         == {"table", "column", "transformation_type",
             "transformation_logic", "role"}),
        ("a view source keeps its schema and alias, in order",
         list(view_src.to_dict())
         == ["schema", "table", "column", "alias", "transformation_type",
             "transformation_logic", "role"]),
        ("ABSENT and None are not the same thing",
         archive_src.schema is ABSENT and view_src.schema == "CRMDB_UAT"
         and Source.from_dict({"schema": None}).schema is None),

        # 2. the description slot
        ("with_description writes the meaning to the FIELD",
         described.description == "Mã địa chỉ"),
        ("...and changes nothing a source file could prove",
         described.lineage == original.lineage),
        ("...without mutating the record it came from",
         original.description is None),

        # 3. the schema is live, and cannot drift again
        ("both record shapes validate against lineage.json",
         len(violations) == 0),
        ("the real schema and the real types agree",
         entities.reconcile_with_schema(SCHEMA) is None),
        ("a schema that drops a field the types have is rejected",
         reconcile_rejects(lambda s: s["items"]["properties"]["lineage"]["items"]
                           ["properties"].pop("schema"))),
        ("a schema that adds a field the types lack is rejected",
         reconcile_rejects(lambda s: s["items"]["properties"]
                           .__setitem__("invented", {"type": "string"}))),
        ("a schema missing a whole object is rejected, not skipped",
         reconcile_rejects(lambda s: s["items"]["properties"].pop("lineage"))),

        # 4. whole-dictionary helpers
        ("records_from / records_to round-trip a whole dictionary",
         entities.records_to(entities.records_from(ALL)) == ALL),
    ]

    print()
    print("=" * 74)
    print("ASSERTIONS")
    print("=" * 74)
    failed = 0
    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        failed += not ok
    print(f"\n  {len(checks) - failed}/{len(checks)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main_())
