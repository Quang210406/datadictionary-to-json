"""The Pydantic models are the contract, and adopting them changed nothing.

    python tests/test_templates.py

No API key, no network, nothing stubbed.

The extraction schema is not just a validator — `agent.py` interpolates it
into the prompt with `json.dumps(schema, indent=2)`. So the schema's TEXT is
part of what the model reads, and changing it changes the extraction.

That is why "semantically equivalent" is not the bar here. Two dicts can
compare equal and serialise differently, and Pydantic's own output is
semantically identical to the shipped schemas while being 47% longer and
shaped differently — `anyOf: [{type: X}, {type: null}]` where these files say
`type: [X, null]`.

Worse, such a change would be **invisible**. Cache keys are file content and
kind, never the prompt, so every already-cached file would keep returning its
old answer: the tests would pass, the numbers would still print, and the new
prompt would first take effect months later on a file nobody had cached yet.

So this asserts the strongest available property: the generated schema and the
shipped file produce the **same string**. While that holds, moving the source
of truth into Pydantic is a proved no-op rather than an unmeasured bet.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import jsonschema

import kinds
import templates


def serialised(schema):
    """Exactly what agent.py puts in the prompt."""
    return json.dumps(schema, indent=2, ensure_ascii=False)


def main_():
    failed = 0
    print("=" * 74)
    print("GENERATED vs SHIPPED — the prompt must not change")
    print("=" * 74)

    identical = {}
    for name in templates.MODELS:
        shipped = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        generated = templates.json_schema(name)
        identical[name] = serialised(shipped) == serialised(generated)
        print(f"  {name:<26} {'identical' if identical[name] else 'DIFFERS'}  "
              f"({len(serialised(generated)):,} chars)")

    print()
    print("=" * 74)
    print("THE MODELS ARE REAL PYDANTIC, NOT A FIELD LIST")
    print("=" * 74)
    good = templates.ViewRecord(
        target_table="V", target_column="C", source_schema=None,
        source_table="T", source_column="X", source_alias=None,
        source_role="value", transformation_logic="direct")
    print(f"  a valid record validates      : {good.target_column == 'C'}")

    rejected = []
    for label, kwargs in (
        ("an unknown field", dict(target_table="V", target_column="C",
                                  source_schema=None, source_table=None,
                                  source_column=None, source_alias=None,
                                  source_role=None, transformation_logic=None,
                                  invented="x")),
        ("a bad source_role", dict(target_table="V", target_column="C",
                                   source_schema=None, source_table=None,
                                   source_column=None, source_alias=None,
                                   source_role="nonsense",
                                   transformation_logic=None)),
        ("a missing required field", dict(target_table="V")),
    ):
        try:
            templates.ViewRecord(**kwargs)
        except Exception:
            rejected.append(label)
    print(f"  rejects                       : {rejected}")

    # The generated schema must still work as a validator, not only as text.
    sample = [good.model_dump()]
    errors = list(jsonschema.Draft202012Validator(
        templates.json_schema("view_record.json")).iter_errors(sample))

    # Every kind kinds.py registers must have a model behind it, or a run would
    # fail at load_schemas() — which is reached before any file is read.
    missing = sorted(set(kinds.schema_files().values()) - set(templates.MODELS))

    import main
    served = main.load_schemas()

    checks = [
        ("every shipped schema is generated character-for-character",
         all(identical.values())),
        ("...which means the prompt text is unchanged",
         all(identical.values())),
        ("every registered source kind has a model",
         missing == []),
        ("the generated schema still validates a real record",
         errors == []),
        ("the models reject an unknown field",
         "an unknown field" in rejected),
        ("the models reject a role outside the enum",
         "a bad source_role" in rejected),
        ("the models reject a missing required field",
         "a missing required field" in rejected),
        ("a nullable enum admits null as a VALUE, not only as a type",
         None in templates.json_schema(
             "view_record.json")["items"]["properties"]["source_role"]["enum"]),
        ("required order follows the model, so key order is stable",
         templates.json_schema("view_record.json")["items"]["required"]
         == list(templates.ViewRecord.model_fields)),
        ("every schema carries the $comment that explains it",
         all(templates.json_schema(n)["$comment"] for n in templates.MODELS)),
        # Asserted, not assumed: the point of the whole exercise is that the
        # RUNNING program uses the models, not the files on disk.
        ("main.load_schemas() serves the generated schemas, not the files",
         served == {k: templates.json_schema(f)
                    for k, f in kinds.schema_files().items()}),
    ]

    print()
    print("=" * 74)
    print("ASSERTIONS")
    print("=" * 74)
    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        failed += not ok
    print(f"\n  {len(checks) - failed}/{len(checks)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main_())
