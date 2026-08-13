import jsonschema

from assemble import ARCHIVE_STAGES, field_key, format_key

MIN_PLAUSIBLE_COLUMNS = 3

# Keys whose values must exist verbatim in the source text. These are the
# identifiers the whole assembly hangs on, and the ones an AI would most
# plausibly "helpfully" normalise. They cover all three schemas: flat hop and
# DDL records, and the nested lineage entries and their sources.
FIDELITY_KEYS = (
    "table",
    "column",
    "source_schema",
    "target_table",
    "target_column",
    "source_table",
    "source_column",
)

DIAGNOSTIC_EXAMPLES = 5

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

# Checkpoint 1 for a text source. A .sql file has no rows or columns to count,
# so the equivalent sanity check is that it holds a view definition at all.
def validate_sql_input(text) -> list:
    errors = []
    if not text or not text.strip():
        errors.append("SQL file is empty.")
    elif "select" not in text.lower():
        errors.append("SQL file contains no SELECT; not a view definition.")
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
# expected_count may be None when the row count of a source is not
# recoverable from its layout; the count is then reported, not judged.
def _check_completeness(result, expected_count):
    """Did every input row / declared column produce a record?

    Returns (errors, records emitted, target fields covered). The two counts
    differ under n-1, where one target field legitimately produces several
    records, so both are reported: the check is on FIELDS, and quoting the
    record count alone reads like a failure when nothing is wrong.
    """
    errors = []
    got_count = len(result) if isinstance(result, list) else 0
    if expected_count is None or not isinstance(result, list):
        return errors, got_count, got_count
    # One INPUT ROW is one target field. n-1 turns that row into several
    # records sharing a target, so the invariant is the number of distinct
    # target fields, not the number of records.
    targets = {
        str(r.get("target_column", "")).strip().upper()
        for r in result
        if isinstance(r, dict) and r.get("target_column")
    }
    covered = len(targets) if targets else got_count
    if covered != expected_count:
        errors.append(
            f"Completeness mismatch: expected {expected_count} target field(s), "
            f"got {covered} (from {got_count} records)."
        )
    return errors, got_count, covered

# fidelity (only meaningful if we actually got a list of records)
# Walks records of any shape, so the same check covers the flat agent
# outputs and the nested assembled lineage.
def _check_fidelity(result, source_text):
    errors = []
    fidelity_checked = 0   # non-null table/column values we could verify
    fidelity_missing = 0   # of those, values not found in the source
    null_count = 0         # nulls are reported, not judged: they may be faithful gaps

    def walk(node, path):
        nonlocal fidelity_checked, fidelity_missing, null_count
        if isinstance(node, dict):
            for key, value in node.items():
                if value is None:
                    null_count += 1
                elif isinstance(value, (dict, list)):
                    walk(value, f"{path}.{key}")
                elif key in FIDELITY_KEYS and isinstance(value, str):
                    fidelity_checked += 1
                    if value not in source_text:
                        fidelity_missing += 1
                        errors.append(
                            f"{path}.{key}: '{value}' not found in source "
                            "— possible fabrication"
                        )
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    if isinstance(result, list):
        for i, record in enumerate(result):
            if not isinstance(record, dict):
                continue  # schema check already reported this
            walk(record, f"Record {i}")
    return errors, fidelity_checked, fidelity_missing, null_count

# Checkpoint 2: verify the AI's output after the call.
# This is the "Calculate accuracy" step from the architecture diagram:
# the same checks that gate the run also produce the accuracy metrics,
# so the numbers can never disagree with the pass/fail decision.
# Three independent checks:
#   shape        : conforms to the schema for this source kind
#   completeness : record count matches the input (no added/dropped/merged rows)
#   fidelity     : every table/column value exists verbatim (word for word) in the source text
#                  (the "never invent values" rule, enforced mechanically)
# Returns {"errors": [...], "metrics": {...}}.
def validate_output(result, expected_count, schema, source_text: str) -> dict:
    shape_errors, dirty_records = _check_shape(result, schema)
    count_errors, got_count, covered = _check_completeness(result, expected_count)
    fidelity_errors, fidelity_checked, fidelity_missing, null_count = _check_fidelity(
        result, source_text
    )

    # error order preserved from the single-function version:
    # shape, then completeness, then fidelity
    errors = shape_errors + count_errors + fidelity_errors

    metrics = {
        # What the completeness check actually tested, and the record count
        # separately: under n-1 the two differ and conflating them misleads.
        "fields_covered": f"{covered}/"
        f"{expected_count if expected_count is not None else 'unknown'}",
        "records_emitted": got_count,
        "schema_clean_records": f"{got_count - len(dirty_records)}/{got_count}",
        "fidelity_verified": f"{fidelity_checked - fidelity_missing}/{fidelity_checked}",
        "output_null_count": null_count,
    }
    return {"errors": errors, "metrics": metrics}


def _sorted_stage_keys(stage_keys):
    return sorted(stage_keys, key=lambda pair: (pair[0], pair[1][0] or "", pair[1][1]))


def _counted(items, render):
    return {
        "count": len(items),
        "examples": [render(item) for item in items[:DIAGNOSTIC_EXAMPLES]],
    }


# Where the hop chain came apart: the keys that STILL do not match once
# normalization has absorbed the case and whitespace differences.
#
# A hop record joins to the chain before it on (table, column). When that
# join fails, nothing raises — the run simply yields two short chains where
# one long one was expected, which is invisible in a record count. This names
# the two ends of every such break:
#
#   unmatched_tails — a chain that stops before the last stage: no later hop
#                     claimed this key as its source.
#   unmatched_heads — a chain that starts after the first stage: no earlier
#                     hop produced the key this one reads from.
#
# A break shows up in BOTH lists, at the same stage, and the two spellings
# side by side are the diagnosis: if normalization could have saved them they
# would already have matched, so whatever differs is real (STG_FDM_TRAN_HIS
# vs FDM_TRAN_HIS is a different table, not different formatting).
#
# Reported, never errors — a field genuinely ending mid-pipeline looks
# identical to a break, and only someone who knows the platform can say
# which it is. What the number is good for is movement: complete_chains
# dropping is a chaining regression.
def chain_diagnostics(lineage_records, stage_names) -> dict:
    first_stage, last_stage = stage_names[0], stage_names[-1]
    complete_chains = 0
    unmatched_tails, unmatched_heads = set(), set()

    for record in lineage_records:
        chain = record["lineage"]
        head, tail = chain[0], chain[-1]
        starts_at_first = head["stage"] == first_stage
        reaches_last = tail["stage"] == last_stage

        if starts_at_first and reaches_last:
            complete_chains += 1

        if not reaches_last:
            key = field_key(tail["table"], tail["column"])
            if key is not None:
                unmatched_tails.add((tail["stage"], key))

        # An empty sources list marks the source side of a hop: a real
        # upstream key that no earlier hop produced. A head with a populated
        # sources list is a field whose sheet stated no source at all, so
        # there was never anything for it to match.
        if not starts_at_first and not head["sources"]:
            key = field_key(head["table"], head["column"])
            if key is not None:
                unmatched_heads.add((head["stage"], key))

    render = lambda pair: f"{pair[0]}: {format_key(pair[1])}"
    return {
        "stages": list(stage_names),
        "chains": len(lineage_records),
        "complete_chains": complete_chains,
        "unmatched_tails": _counted(_sorted_stage_keys(unmatched_tails), render),
        "unmatched_heads": _counted(_sorted_stage_keys(unmatched_heads), render),
    }


# Checkpoint 4: how complete the assembled dictionary is, per column, so a
# person can look at one table and decide whether it is fit to hand over.
# These are counts, never errors — a blank is often the truthful answer.
COVERAGE_STAGES = ARCHIVE_STAGES


def coverage_metrics(lineage_records, stages=COVERAGE_STAGES) -> dict:
    total = len(lineage_records)
    if not total:
        return {"records": 0}
    stage_present = {s: 0 for s in stages}
    datatype_present = {s: 0 for s in stages}
    described = full_chain = with_logic = multi_source = 0
    targets = {}
    for record in lineage_records:
        by_stage = {e["stage"]: e for e in record["lineage"]}
        for s in stages:
            if s in by_stage:
                stage_present[s] += 1
                if by_stage[s].get("datatype"):
                    datatype_present[s] += 1
        if record.get("description"):
            described += 1
        if all(s in by_stage for s in stages):
            full_chain += 1
        if any(src.get("transformation_logic")
               for entry in record["lineage"] for src in entry["sources"]):
            with_logic += 1
        last = record["lineage"][-1]
        key = (last["table"], last["column"]) if last["stage"] != "cloud" else None
        for entry in record["lineage"]:
            if entry["stage"] == "dwh":
                key = (entry["table"], entry["column"])
        if key:
            targets[key] = targets.get(key, 0) + 1
    multi_source = sum(1 for n in targets.values() if n > 1)
    pct = lambda n: f"{n}/{total} ({n / total:.0%})"
    return {
        "records": total,
        "distinct_target_fields": len(targets),
        "n_to_1_target_fields": multi_source,
        "complete_chains": pct(full_chain),
        "with_description": pct(described),
        "with_transformation_logic": pct(with_logic),
        **{f"stage_{s}": pct(stage_present[s]) for s in stages},
        **{f"datatype_{s}": pct(datatype_present[s]) for s in stages
           if datatype_present[s]},
    }
