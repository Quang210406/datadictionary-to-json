import sys, os, json
import pandas as pd
from dotenv import load_dotenv
from google import genai
import jsonschema

MIN_PLAUSIBLE_COLUMNS = 3

# Load GEMINI_API_KEY from the .env file into the environment.
load_dotenv()

# Read one sheet as a raw grid: drop fully empty rows
def read_excel_df(path: str, sheet_name="Mapping") -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name, header=None)
    return df.dropna(how="all")

# Turn the raw grid into plain CSV text for the AI agent to read.
def df_to_text(df: pd.DataFrame) -> str:
    return df.to_csv(index=False, header=False)

# Checkpoint 1: check the input before spending an API call.
# check if the input has data and if the input has enough columns
# to be a data frame (assumption: a proper data dictionary has 3 columns)
def validate_input(df: pd.DataFrame) -> list:
    errors = []
    if df.empty:
        errors.append("Input sheet has no data rows after dropping fully-empty rows.")
    if df.shape[1] < MIN_PLAUSIBLE_COLUMNS:
        errors.append(
            f"Input sheet has only {df.shape[1]} column(s); "
            "a mapping table needs at least 3."
        )
    return errors

# Checkpoint 2: verify the AI's output after the call.
# Three independent checks:
#   shape        : conforms to schema.json
#   completeness : record count matches the input (no added/dropped/merged rows)
#   fidelity     : every table/column value exists verbatim (word for word) in the source text
#                  (the "never invent values" rule, enforced mechanically)
def validate_output(result, expected_count: int, schema, source_text: str) -> list:
    errors = []

    # shape
    validator = jsonschema.Draft202012Validator(schema)
    for err in validator.iter_errors(result):
        errors.append(f"Schema violation at {err.json_path}: {err.message}")

    # completeness
    if isinstance(result, list) and len(result) != expected_count:
        errors.append(
            f"Record count mismatch: expected {expected_count}, got {len(result)}."
        )

    # fidelity (only meaningful if we actually got a list of records)
    if isinstance(result, list):
        for i, record in enumerate(result):
            if not isinstance(record, dict):
                continue  # schema check already reported this
            for hop in record.get("lineage", []):
                for key in ("table", "column"):
                    v = hop.get(key)
                    if v is not None and v not in source_text:
                        errors.append(
                            f"Record {i}, {hop.get('stage')}.{key}: "
                            f"'{v}' not found in source — possible fabrication"
                        )
    return errors

# Sends dictionary text to AI agent
def convert(text, schema) -> list:
    prompt = f"""You are a data restructuring tool. Convert the data dictionary
below into a JSON array conforming exactly to this JSON Schema:

{json.dumps(schema, indent=2)}

The sheet is a lineage mapping: header rows describe stage groups of
columns (source_onprem, staging, dwh, cloud), then each data row is one
field's journey through those stages.

Rules:
- One JSON record per data row. Never add, drop, or merge records.
- Each record's "lineage" lists the stages the field appears in, in
  pipeline order: source_onprem, staging, dwh, cloud.
- If a field is absent from a stage entirely, OMIT that stage from its
  lineage — do not emit a null-filled entry.
- If a stage is present but a value (table, column, doc_link,
  offline_path) is unknown or blank, use null for that value.
- Restructure only. NEVER invent values.
- Output ONLY the JSON array. No markdown, no explanation.

DATA DICTIONARY:
{text}"""

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt,
    )

    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").removeprefix("json").strip()
    return json.loads(raw)

def main():
    df = read_excel_df(sys.argv[1])

    errors = validate_input(df)
    if errors:
        print("Input validation failed:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    # subtract the 3 header rows (environment, stage, column names)
    expected_count = len(df) - 3

    schema = json.load(open("schema.json"))
    text = df_to_text(df)                      
    result = convert(text, schema)
    errors = validate_output(result, expected_count, schema, text)
    if errors:
        print("Output validation failed:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    json.dump(result, open("output.json", "w"), indent=2, ensure_ascii=False)
    print(f"OK: wrote {len(result)} records to output.json")

if __name__ == "__main__":
    main()

