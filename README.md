# Datadictionary-to-json
Converts data dictionaries into structured JSON
using an AI agent constrained by a predefined JSON Schema.
## Implemented so far

**Core pipeline**: runs end to end on a synthetic sample file:

- `excel_to_text()`: extracts one sheet as raw CSV-style text. Skips fully empty rows only, so records with missing
  values survive intact.
- `convert()`: sends the text plus `schema.json` to Gemini
  (`gemini-3.5-flash`). The agent restructures only:
  never invents values (missing → null), never adds, drops, or merges
  records. 
- `schema.json`: the output contract: 8 fields per record, only `table`
  and `field` required, all others explicitly nullable,
  `additionalProperties: false`.
- `main.py`: CLI entry point; writes `output.json`.

Verified on the sample: 8/8 records converted, blank table-name cells
correctly carried down, deliberately-missing values preserved as null.
## Architecture ![architecture](architecturev2.png)