import os, json
from dotenv import load_dotenv
from google import genai

# Load GEMINI_API_KEY from the .env file into the environment.
# Lives here (not main.py) because this module is the only consumer of
# the key — anything importing convert() gets a working setup for free.
load_dotenv()

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
