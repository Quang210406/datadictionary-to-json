"""The assembled dictionary in code form: Source, StageEntry, Record.

`schemas/lineage.json` has always defined this shape exactly, and was
referenced nowhere. A schema nothing loads is not documentation, it is a
guess about the past: by the time this module was written the real records
had grown four fields the schema forbade — `schema` and `role` on every
record, `alias` on view sources, `resolved_source` on chained ones — and
validating against it would have rejected 100% of both dictionaries (444
violations on the archive, 1513 on the views). Nothing noticed, because
nothing asked.

So this module does two things:

  * gives the shape a typed form, so a description can be written to
    `Record.description` rather than to `record["lineage"][2]["description"]`
  * reconciles itself with `schemas/lineage.json` at load time, so the schema
    can never silently drift out of date again

That second half is the same arrangement agent.py has with kinds.py: two
files that must agree, with the agreement checked rather than assumed. It is
the only thing that makes the first half trustworthy — a type that disagrees
with the schema is just a fifth place to declare the same thing.

These are a typed VIEW over the records, not a new format. assemble.py still
builds plain dicts, and `Record.from_dict(d).to_dict() == d` for every record
either mode produces, key order included. Nothing downstream has to change to
use them, and nothing downstream breaks if it does not.
"""

from dataclasses import dataclass, fields
from typing import Any, List, Optional

from assemble import field_key, target_entry, target_key

# Distinct from None, and the distinction is load-bearing.
#
#   None    the source states the field and it is empty
#   ABSENT  the field is not a thing this kind of source HAS
#
# A hop specification has no schema and no alias — a spreadsheet row names a
# table and a column and nothing else — so those keys are not in an archive
# record at all. A view states both, and states them as null when the SQL does
# not say. Collapsing the two would put `"schema": null` into 83 archive
# records that never had it, changing a published artefact to make this
# module's life easier. The data decides the shape; the shape does not get to
# tidy the data.
class _Absent:
    __slots__ = ()

    def __repr__(self):
        return "ABSENT"

    def __bool__(self):
        return False


ABSENT = _Absent()


def _emit(pairs) -> dict:
    """A dict of the pairs whose value is not ABSENT, in the order given.

    Order is not cosmetic here: it is what makes the round-trip byte-exact
    against the JSON assemble.py writes, so these types can be adopted one
    call site at a time without a diff appearing in the output.
    """
    return {key: value for key, value in pairs if value is not ABSENT}


@dataclass(frozen=True)
class Source:
    """One field feeding one stage entry, and how.

    One record is one (target field, source field) pair, so a field with ten
    sources is ten records — this is that "source field" half.
    """

    table: Optional[str]
    column: Optional[str]
    transformation_type: Optional[str]
    transformation_logic: Optional[str]
    role: Optional[str]
    # Stated by SQL sources only; see ABSENT above.
    schema: Any = ABSENT
    alias: Any = ABSENT

    def to_dict(self) -> dict:
        # Two orders because there are two shapes, and each reproduces the
        # order its builder in assemble.py writes (_source_of, _view_source).
        if self.schema is ABSENT and self.alias is ABSENT:
            return _emit([
                ("table", self.table), ("column", self.column),
                ("transformation_type", self.transformation_type),
                ("transformation_logic", self.transformation_logic),
                ("role", self.role)])
        return _emit([
            ("schema", self.schema), ("table", self.table),
            ("column", self.column), ("alias", self.alias),
            ("transformation_type", self.transformation_type),
            ("transformation_logic", self.transformation_logic),
            ("role", self.role)])

    @classmethod
    def from_dict(cls, data: dict) -> "Source":
        return cls(
            table=data.get("table"), column=data.get("column"),
            transformation_type=data.get("transformation_type"),
            transformation_logic=data.get("transformation_logic"),
            role=data.get("role"),
            schema=data["schema"] if "schema" in data else ABSENT,
            alias=data["alias"] if "alias" in data else ABSENT)


@dataclass(frozen=True)
class StageEntry:
    """The field as it exists at ONE stage, and the evidence for it.

    offline_path is the file this stage's facts were read from — the "Đường
    dẫn" column of the hand-built dictionary. It is what makes a value
    checkable: every string here can be found in that one file.
    """

    stage: str
    schema: Optional[str]
    table: Optional[str]
    column: Optional[str]
    datatype: Optional[str]
    size: Optional[str]
    constraint: Optional[str]
    doc_link: Optional[str]
    offline_path: Optional[str]
    sources: List[Source]

    def to_dict(self) -> dict:
        return {
            "stage": self.stage, "schema": self.schema, "table": self.table,
            "column": self.column, "datatype": self.datatype,
            "size": self.size, "constraint": self.constraint,
            "doc_link": self.doc_link, "offline_path": self.offline_path,
            "sources": [s.to_dict() for s in self.sources],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StageEntry":
        return cls(
            stage=data["stage"], schema=data.get("schema"),
            table=data.get("table"), column=data.get("column"),
            datatype=data.get("datatype"), size=data.get("size"),
            constraint=data.get("constraint"), doc_link=data.get("doc_link"),
            offline_path=data.get("offline_path"),
            sources=[Source.from_dict(s) for s in data.get("sources") or []])


@dataclass(frozen=True)
class ResolvedSource:
    """Where a SQL source ultimately comes from, when it was itself a view.

    Recorded beside the chain rather than inside it: the extraction asserts
    one hop, which is what a single file can prove. Following the hop is a
    separate deterministic step, so it is a separate field.
    """

    schema: Optional[str]
    table: Optional[str]
    column: Optional[str]
    via: List[str]

    def to_dict(self) -> dict:
        return {"schema": self.schema, "table": self.table,
                "column": self.column, "via": list(self.via)}

    @classmethod
    def from_dict(cls, data: dict) -> "ResolvedSource":
        return cls(schema=data.get("schema"), table=data.get("table"),
                   column=data.get("column"), via=list(data.get("via") or []))


@dataclass(frozen=True)
class Record:
    """One field, traced through every stage that touched it.

    `description` is the field's business meaning. It is the project's largest
    gap against the requirement — where no source states a meaning it is None,
    because nothing here generates one. Naming it a field of the record rather
    than an entry buried in a list is the point: a description belongs to the
    FIELD, not to any one stage's copy of it, so there is exactly one place to
    write it and exactly one place to read it.
    """

    description: Optional[str]
    lineage: List[StageEntry]
    resolved_source: Any = ABSENT

    def to_dict(self) -> dict:
        return _emit([
            ("description", self.description),
            ("lineage", [e.to_dict() for e in self.lineage]),
            ("resolved_source",
             self.resolved_source.to_dict()
             if isinstance(self.resolved_source, ResolvedSource)
             else self.resolved_source)])

    @classmethod
    def from_dict(cls, data: dict) -> "Record":
        resolved = ABSENT
        if "resolved_source" in data:
            value = data["resolved_source"]
            resolved = ResolvedSource.from_dict(value) if value else value
        return cls(
            description=data.get("description"),
            lineage=[StageEntry.from_dict(e) for e in data.get("lineage") or []],
            resolved_source=resolved)

    # --- the slot Hồng Ngọc's descriptions attach to ----------------------

    def with_description(self, description) -> "Record":
        """The same record, carrying a meaning.

        Returns a new Record because these are frozen: a description arriving
        from elsewhere must not be able to mutate a record another part of the
        run is still reading. Nothing about the lineage is touched, so a
        described record and its undescribed original still agree
        field-for-field on everything a source file can prove.
        """
        return Record(description=description, lineage=self.lineage,
                      resolved_source=self.resolved_source)


def records_from(raw) -> List[Record]:
    """A whole dictionary, as read from output.json / views.json."""
    return [Record.from_dict(r) for r in raw]


def records_to(records) -> list:
    """...and back to exactly the JSON it came from."""
    return [r.to_dict() for r in records]


# --------------------------------------------------------- reconciliation

# Which dataclass mirrors which object in schemas/lineage.json. The schema is
# nested, so this names the path to each object rather than assuming a flat
# file.
_SCHEMA_PATHS = {
    "Record": ("items",),
    "StageEntry": ("items", "properties", "lineage", "items"),
    "Source": ("items", "properties", "lineage", "items",
               "properties", "sources", "items"),
}
_TYPES = {"Record": Record, "StageEntry": StageEntry, "Source": Source}


def _dig(schema, path):
    for step in path:
        schema = schema[step]
    return schema


def reconcile_with_schema(schema) -> None:
    """Fail loudly if the types and schemas/lineage.json disagree.

    Called once per run, from main, rather than at import: main.SCHEMA_DIR is
    corrected by the desktop app after import, because a frozen bundle does
    not preserve the path a module computes from its own __file__. A module
    that read the schema at import time would work from source and break in
    the app, which is the worst of both.

    Every mismatch below is a drift that used to be invisible. The schema
    forbade `role`, `schema`, `alias` and `resolved_source` for weeks while
    the code emitted all four, and nothing said so because nothing compared
    them.
    """
    for name, path in _SCHEMA_PATHS.items():
        try:
            node = _dig(schema, path)
        except (KeyError, TypeError):
            raise ValueError(
                f"schemas/lineage.json has no object at {'.'.join(path)}, "
                f"which is where {name} should be described.") from None

        declared = set(node.get("properties", {}))
        typed = {f.name for f in fields(_TYPES[name])}
        if declared != typed:
            missing = sorted(typed - declared)
            extra = sorted(declared - typed)
            raise ValueError(
                f"{name} and schemas/lineage.json disagree: "
                + (f"the schema does not describe {missing}; " if missing else "")
                + (f"the schema describes {extra}, which the type has not; "
                   if extra else "")
                + "one of the two has drifted, and a dictionary validated "
                  "against the schema would be judged by the wrong shape.")


# ------------------------------------------------------- the domain view
#
# Everything above is the STORAGE shape — how a record is written to
# output.json and read back. What follows is the same data in the vocabulary
# the field already uses: a Table has Columns, a Column has a Lineage.
#
# These compute nothing new. `Column.key` is `field_key(*target_key(record))`
# and `Column.table`/`Column.name` are the exact `target_key` tuple, both taken
# by CALLING those functions. That restraint is the whole design: assemble.py
# holds the only two definitions of "the same field", and target_key's own
# docstring records what happened the last time a second copy existed — it
# drifted, and the drift read to a reviewer as one of the two being broken.
#
# What the domain view is FOR: a description belongs to a Column, not to a
# record. One record is one (target field, source field) pair, so a field fed
# by ten sources is ten records carrying one meaning. Naming the Column makes
# that a fact about the model rather than a rule someone has to remember.


@dataclass(frozen=True)
class Lineage:
    """One field's path, origin first, the stage that produced it last."""

    stages: List[StageEntry]

    @property
    def origin(self):
        return self.stages[0] if self.stages else None

    @property
    def target(self):
        return self.stages[-1] if self.stages else None

    @property
    def stage_names(self) -> List[str]:
        return [entry.stage for entry in self.stages]

    @property
    def sources(self) -> List[Source]:
        """Every source named anywhere along the chain."""
        return [src for entry in self.stages for src in entry.sources]


@dataclass(frozen=True)
class Column:
    """One field of one table: what it is, what it means, where it came from.

    `description` is what a source document stated, or None. Text a person
    wrote is deliberately NOT here — it lives in a separate overlay
    (`descriptions.py`), because a copied sentence can be checked
    character-for-character against its file and an authored one cannot, and
    one attribute holding both would make that difference unrecoverable.
    """

    table: Optional[str]        # the dictionary's own spelling
    name: str                   # ditto
    key: Any                    # normalised, for matching
    stage: str
    datatype: Optional[str]
    size: Optional[str]
    description: Optional[str]
    evidence: Optional[str]     # the file this field's facts were read from
    lineages: List[Lineage]     # one per (field, source) pair — n->1 gives many

    @property
    def is_fan_in(self) -> bool:
        return len(self.lineages) > 1


@dataclass(frozen=True)
class Table:
    """A named table and the columns this dictionary knows about it.

    Grouped on the EXACT table name and nothing else. It deliberately does not
    decide whether `DWH_TXN_HISTORY` and `TXN_HISTORY` are one table — the
    cloud lookup strips warehouse prefixes and treats them as the same,
    field_key treats them as different, and nothing in the system has ever had
    to reconcile the two. Answering that here would bury a real ambiguity
    inside a dataclass; leaving it means a Table is exactly what the documents
    call one, which is also what makes `Table.name` a rule someone can write
    down: it is the sheet name, never the row cell.
    """

    name: Optional[str]
    stage: str
    columns: List[Column]


def columns_from(records) -> List[Column]:
    """The distinct fields of a dictionary, in first-seen order."""
    grouped, order = {}, []
    for raw in records:
        record = raw if isinstance(raw, Record) else Record.from_dict(raw)
        plain = raw if isinstance(raw, dict) else raw.to_dict()
        key = target_key(plain)
        if key is None:
            continue
        match = field_key(*key)
        if match not in grouped:
            order.append(match)
            grouped[match] = {"key": key, "records": [], "entries": []}
        grouped[match]["records"].append(record)
        grouped[match]["entries"].append(target_entry(plain) or {})

    out = []
    for match in order:
        bundle = grouped[match]
        table, name = bundle["key"]
        first = bundle["entries"][0]
        described = next((r.description for r in bundle["records"] if r.description),
                         None)
        out.append(Column(
            table=table, name=name, key=match,
            stage=first.get("stage") or "",
            datatype=first.get("datatype"), size=first.get("size"),
            description=described, evidence=first.get("offline_path"),
            lineages=[Lineage(stages=list(r.lineage)) for r in bundle["records"]]))
    return out


def tables_from(records) -> List[Table]:
    """The distinct tables, each carrying its columns."""
    grouped, order = {}, []
    for column in columns_from(records):
        if column.table not in grouped:
            order.append(column.table)
            grouped[column.table] = []
        grouped[column.table].append(column)
    return [Table(name=name, stage=grouped[name][0].stage,
                  columns=grouped[name]) for name in order]
