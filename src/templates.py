"""The extraction contract, as Pydantic models.

What the agent must return for each source kind used to live only in
`schemas/*.json`, hand-written. Those files do two jobs at once: they are
pasted verbatim into the prompt, and they validate the reply. That works, and
for four small schemas it was never painful.

It stops working the moment a fifth document format arrives. Adding one meant
hand-writing another JSON Schema, and there is no way to *derive* one from an
example — which is exactly what `docling_graph.templategen` does, and what the
archive being one example among many eventually requires.

So the model is the declaration and the JSON Schema is generated from it.

**Generated to match what was already shipped, exactly.** The schema is
interpolated into the prompt, so changing its text changes what the model
reads. Pydantic's own `model_json_schema()` renders an optional field as
`anyOf: [{type: X}, {type: null}]` with a `title`, where these schemas say
`type: [X, null]` and no title — semantically identical, textually 47% longer.
Swapping one for the other would silently re-measure a project whose headline
numbers were obtained with the shorter form, and the cache would hide it: cache
keys are file content and kind, never the prompt, so every cached file would
keep returning its old answer and the change would only surface months later,
on somebody else's watch.

`_normalise` below therefore folds Pydantic's output back into the shipped
shape, and `tests/test_templates.py` asserts the two serialise identically.
While that test passes, adopting these models is a proved no-op.
"""

from typing import List, Literal, Optional, Type

from pydantic import BaseModel

# The roles a source can play, shared by both mapping kinds so the two cannot
# drift into offering different vocabularies for the same idea.
Role = Literal["value", "join", "condition"]


class HopRecord(BaseModel):
    """One row of a hop specification: one target field and one source field."""

    model_config = {"extra": "forbid", "json_schema_extra": {"$comment": (
        "One record per (target field, source field) pair in a hop spec. n-1 "
        "is expressed as SEVERAL records sharing one target_column — never as "
        "one record with stuffed cells. Datatype and size are captured at BOTH "
        "ends because they change across a hop in ~10% of rows. Every key is "
        "required so unknowns are explicit nulls; target_column is the join "
        "key, so it is the one value that may not be null."
    )}}

    # Nullable because a row may leave the cell blank and inherit the
    # sheet-level Target Table Name; target_column is the join key and is the
    # one value that may not be null.
    target_table: Optional[str]
    target_column: str
    target_datatype: Optional[str]
    target_size: Optional[str]
    source_table: Optional[str]
    source_column: Optional[str]
    source_datatype: Optional[str]
    source_size: Optional[str]
    transformation_type: Optional[str]
    transformation_logic: Optional[str]
    source_role: Optional[Role]


class CloudRecord(BaseModel):
    """One column of one table as it lands in the final stage."""

    model_config = {"extra": "forbid", "json_schema_extra": {"$comment": (
        "One record per row of a per-table sheet in the DWH->CLOUD reference "
        "workbook."
    )}}

    table: Optional[str]
    column: str
    datatype: Optional[str]
    size: Optional[str]
    nullable: Optional[str]
    description: Optional[str]


class ViewRecord(BaseModel):
    """One (declared column, source field) pair of a CREATE statement."""

    model_config = {"extra": "forbid", "json_schema_extra": {"$comment": (
        "One record per (declared view column, source field) pair in a CREATE "
        "VIEW script. n-1 is several records sharing one target_column. Field "
        "names deliberately match hop_record where the meaning matches, so the "
        "completeness and fidelity checks work unchanged. No datatype/size: a "
        "view declares neither."
    )}}

    target_table: str
    target_column: str
    source_schema: Optional[str]
    source_table: Optional[str]
    source_column: Optional[str]
    source_alias: Optional[str]
    source_role: Optional[Role]
    transformation_logic: Optional[str]


class DocDescription(BaseModel):
    """One field meaning a prose document actually states."""

    model_config = {"extra": "forbid", "json_schema_extra": {"$comment": (
        "What a prose document (PDF, Word) states about a field's MEANING. "
        "Not lineage: a design document says what a column is for, not which "
        "staging table it came from. One record per (table, column) the "
        "document actually defines. 'section' records where in the document "
        "the definition was found — the heading or table caption — because the "
        "deliverable this feeds asks not just what a document says but which "
        "part of it said so."
    )}}

    table: Optional[str]
    column: str
    description: str
    section: Optional[str]


# Which model is the contract for which schema file. The file name is the link,
# because kinds.py already names a schema_file per source kind and nothing here
# should become a second place that decides which kind uses what.
MODELS = {
    "hop_record.json": HopRecord,
    "cloud_record.json": CloudRecord,
    "view_record.json": ViewRecord,
    "doc_description.json": DocDescription,
}


def _normalise(prop: dict) -> dict:
    """One Pydantic property, in the form these schemas have always used.

    Pydantic renders `Optional[X]` as a two-branch `anyOf` and adds a `title`.
    Both are correct JSON Schema and neither is what is shipped. Folding them
    back is what keeps the prompt text unchanged — see the module docstring for
    why that matters more than it looks.
    """
    branches = prop.get("anyOf")
    if not branches:
        # A required field: keep type and enum, drop Pydantic's title.
        return {k: v for k, v in prop.items() if k in ("type", "enum")}

    nullable = any(b.get("type") == "null" for b in branches)
    real = [b for b in branches if b.get("type") != "null"]
    if len(real) != 1:
        raise ValueError(
            f"cannot normalise a union of {len(real)} non-null branches: "
            f"{prop}. These schemas only ever express 'X or null'.")

    inner = real[0]
    out = {"type": [inner["type"], "null"] if nullable else inner["type"]}
    if "enum" in inner:
        # A nullable enum must admit null as a value, not only as a type —
        # the hand-written schemas list it explicitly and a reply of null
        # would otherwise fail validation.
        out["enum"] = list(inner["enum"]) + ([None] if nullable else [])
    return out


def json_schema(schema_file: str) -> dict:
    """The JSON Schema for one source kind, generated from its model.

    Key order follows the model's field order, because `agent.py` interpolates
    `json.dumps(schema, indent=2)` into the prompt and two dicts that compare
    equal can still serialise differently.
    """
    try:
        model: Type[BaseModel] = MODELS[schema_file]
    except KeyError:
        raise ValueError(
            f"No model for {schema_file!r}; have {sorted(MODELS)}") from None

    generated = model.model_json_schema()
    properties = {name: _normalise(generated["properties"][name])
                  for name in model.model_fields}

    comment = (model.model_config.get("json_schema_extra") or {}).get("$comment")
    return {
        "$comment": comment,
        "type": "array",
        "items": {
            "type": "object",
            "properties": properties,
            "required": list(model.model_fields),
            "additionalProperties": False,
        },
    }


def all_schemas() -> dict:
    """{schema file name -> generated schema}, for loading them all at once."""
    return {name: json_schema(name) for name in MODELS}


def _check():
    """Every model must be renderable at import, not at the first API call."""
    for name in MODELS:
        schema = json_schema(name)
        if not schema["$comment"]:
            raise ValueError(
                f"{name} has no $comment. These explain the contract to whoever "
                "reads the schema next, and the hand-written files all carry "
                "one; a generated file that quietly dropped it would be a "
                "regression nobody would notice.")
        if not schema["items"]["properties"]:
            raise ValueError(f"{name} generated no properties")


_check()
