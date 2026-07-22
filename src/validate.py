import jsonschema

MIN_PLAUSIBLE_COLUMNS = 3

# Checkpoint 1: check the input before spending an API call.
# check if the input has data and if the input has enough columns
# to be a data frame (assumption: a proper data dictionary has 3 columns)
def validate_input(df) -> list:
    errors = []
    if df.empty:
        errors.append("Input sheet has no data rows after dropping fully-empty rows.")
    if df.shape[1] < MIN_PLAUSIBLE_COLUMNS:
        errors.append(
            f"Input sheet has only {df.shape[1]} column(s); "
            "a mapping table needs at least 3."
        )
    return errors

# shape, also track which records have at least one violation
def _check_shape(result, schema):
    errors = []
    validator = jsonschema.Draft202012Validator(schema)
    dirty_records = set()
    for err in validator.iter_errors(result):
        errors.append(f"Schema violation at {err.json_path}: {err.message}")
        # err.path starts with the record index when the violation is
        # inside a record (vs. a top-level problem like "not an array")
        if err.path and isinstance(err.path[0], int):
            dirty_records.add(err.path[0])
    return errors, dirty_records

# completeness
def _check_completeness(result, expected_count):
    errors = []
    got_count = len(result) if isinstance(result, list) else 0
    if isinstance(result, list) and len(result) != expected_count:
        errors.append(
            f"Record count mismatch: expected {expected_count}, got {len(result)}."
        )
    return errors, got_count

# fidelity (only meaningful if we actually got a list of records)
def _check_fidelity(result, source_text):
    errors = []
    fidelity_checked = 0   # non-null table/column values we could verify
    fidelity_missing = 0   # of those, values not found in the source
    null_count = 0         # nulls are reported, not judged: they may be faithful gaps
    if isinstance(result, list):
        for i, record in enumerate(result):
            if not isinstance(record, dict):
                continue  # schema check already reported this
            null_count += sum(1 for v in record.values() if v is None)
            for hop in record.get("lineage", []):
                null_count += sum(1 for v in hop.values() if v is None)
                for key in ("table", "column"):
                    v = hop.get(key)
                    if v is None:
                        continue
                    fidelity_checked += 1
                    if v not in source_text:
                        fidelity_missing += 1
                        errors.append(
                            f"Record {i}, {hop.get('stage')}.{key}: "
                            f"'{v}' not found in source — possible fabrication"
                        )
    return errors, fidelity_checked, fidelity_missing, null_count

# Checkpoint 2: verify the AI's output after the call.
# This is the "Calculate accuracy" step from the architecture diagram:
# the same checks that gate the run also produce the accuracy metrics,
# so the numbers can never disagree with the pass/fail decision.
# Three independent checks:
#   shape        : conforms to schema.json
#   completeness : record count matches the input (no added/dropped/merged rows)
#   fidelity     : every table/column value exists verbatim (word for word) in the source text
#                  (the "never invent values" rule, enforced mechanically)
# Returns {"errors": [...], "metrics": {...}}.
def validate_output(result, expected_count: int, schema, source_text: str) -> dict:
    shape_errors, dirty_records = _check_shape(result, schema)
    count_errors, got_count = _check_completeness(result, expected_count)
    fidelity_errors, fidelity_checked, fidelity_missing, null_count = _check_fidelity(
        result, source_text
    )

    # error order preserved from the single-function version:
    # shape, then completeness, then fidelity
    errors = shape_errors + count_errors + fidelity_errors

    metrics = {
        "record_completeness": f"{got_count}/{expected_count}",
        "schema_clean_records": f"{got_count - len(dirty_records)}/{got_count}",
        "fidelity_verified": f"{fidelity_checked - fidelity_missing}/{fidelity_checked}",
        "output_null_count": null_count,
    }
    return {"errors": errors, "metrics": metrics}
