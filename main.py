import sys, os, json
import pandas as pd
from dotenv import load_dotenv
from google import genai

# Load GEMINI_API_KEY from the .env file into the environment.
load_dotenv()

# Turn one sheet of Exel file to plain text for Ai agent to read
def excel_to_text(path: str, sheet_name=0) -> str:
    df = pd.read_excel(path, sheet_name=sheet_name, header=None)
    df = df.dropna(how="all")                 
    return df.to_csv(index=False, header=False)

# Sends dictionary text to AI agent
def convert(text, schema) -> list:
    prompt = f"""You are a data restructuring tool. Convert the data dictionary
below into a JSON array conforming exactly to this JSON Schema:

{json.dumps(schema, indent=2)}

Rules:
- Restructure only. NEVER invent values. Missing value -> null.
- Never add, drop, or merge entries.
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
    text = excel_to_text(sys.argv[1], sheet_name="Flat Layout")
    schema = json.load(open("schema.json"))
    result = convert(text, schema)
    json.dump(result, open("output.json", "w"), indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()