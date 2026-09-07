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

import hashlib
import json
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


class DocMappingRecord(BaseModel):
    """One mapping a prose document states, as opposed to one meaning."""

    model_config = {"extra": "forbid", "json_schema_extra": {"$comment": (
        "A mapping claim a prose document (PDF, Word) actually states: THIS "
        "column is loaded from THAT column. Distinct from doc_description, "
        "which captures what a field MEANS — a design document does both and "
        "they are different claims with different evidence. One record per "
        "(target field, source field) pair, so n-1 is several records sharing "
        "one target_column. No datatypes: where a document states them it "
        "states them as prose, and a guessed type is worse than a missing one. "
        "target_table is nullable because a mapping table often names the "
        "target once in a caption and never again per row; unlike a workbook "
        "there is no sheet name to fall back on, so a null here is honest and "
        "the assembler records that the subject came from a cell."
    )}}

    target_table: Optional[str]
    target_column: str
    source_table: Optional[str]
    source_column: Optional[str]
    transformation_logic: Optional[str]
    section: Optional[str]


# Which model is the contract for which schema file. The file name is the link,
# because kinds.py already names a schema_file per source kind and nothing here
# should become a second place that decides which kind uses what.
MODELS = {
    "hop_record.json": HopRecord,
    "cloud_record.json": CloudRecord,
    "view_record.json": ViewRecord,
    "doc_description.json": DocDescription,
    "doc_mapping.json": DocMappingRecord,
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


# ------------------------------------------------- contracts generated at run time
#
# `docling_graph.templategen` induces a Pydantic template from example documents
# and renders it to Python SOURCE — deterministically, with its own linter and a
# verification pass, and explicitly "no LLM ever writes code". That is the slot
# this module was always the candidate for, and it is what lets an unfamiliar
# format be read without anyone hand-writing a schema first.
#
# It carries one hazard that has to be closed before it can be used at all.
#
# **The schema is interpolated into the prompt** (agent.convert), and cache keys
# are `kind|sha|section` — file content and kind, NEVER the prompt. A contract
# that changed between runs would therefore keep serving answers extracted under
# the OLD contract, silently, from cache, for as long as the cache survived. The
# module docstring above describes the same trap for hand-edited schemas; a
# generated one makes it likely rather than merely possible.
#
# So a generated contract's hash joins its cache key, and a STATIC one's does
# not. Nothing that has ever been cached is invalidated — the 20 archive, 17 SQL
# and 26 app entries keep their keys byte for byte — while a generated contract
# can never answer for a different one.

# {kind name -> generated JSON Schema}. Empty unless a run generated one.
GENERATED = {}


def register_generated(kind_name, schema) -> None:
    """Declare that this kind's contract was generated, not shipped."""
    GENERATED[kind_name] = schema


def contract_tag(kind_name) -> str:
    """The cache-key fragment identifying this kind's contract.

    Empty for a shipped contract, so every existing cache key is unchanged.
    A short content hash for a generated one, so a changed contract is a
    different key rather than a stale hit.
    """
    schema = GENERATED.get(kind_name)
    if schema is None:
        return ""
    body = json.dumps(schema, sort_keys=True, ensure_ascii=False)
    return "@" + hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]


def templategen_available() -> bool:
    """Whether this build can generate a contract — probed, like readers.py.

    docling-graph pulls docling and LiteLLM behind it, so a small deployment
    will not have it. That is a supported configuration, not an error: the
    feature is simply absent and says so.
    """
    try:
        from docling_graph.templategen import generate_template  # noqa: F401
        return True
    except Exception:
        return False


def generate_module(samples, name, output):
    """Render a Pydantic template module from example documents.

    Returns templategen's own GenerationResult. Two of its properties are the
    reason this is worth wiring rather than reimplementing: the renderer is
    deterministic (no model writes the code), and `output` is written ONLY when
    its verification pass succeeds — so a failed generation leaves no half-file
    for someone to import next week.

    The module is emitted for a person to read. Nothing here imports it back
    automatically: a generated contract still has to be looked at before it
    decides what a dictionary means, and `register_generated` is the explicit
    step that puts it into a cache key.
    """
    if not templategen_available():
        raise RuntimeError(
            "docling-graph is not installed in this build, so a contract "
            "cannot be generated. It pulls docling and LiteLLM behind it; the "
            "small deployment deliberately ships without them.")
    import providers
    from docling_graph.templategen import generate_template
    from docling_graph.templategen.llm_call import build_llm_call_fn

    provider = providers.selected()
    return generate_template(
        list(samples), kind="docs", root=name, output=str(output),
        # The same provider and model the rest of the run uses, so a generated
        # contract cannot quietly come from a different model than the
        # extraction it will govern.
        llm_call_fn=build_llm_call_fn(provider=provider.name,
                                      model=providers.model_for(provider)))


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
