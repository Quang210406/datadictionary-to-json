import sys, json

from extract import read_excel_df, df_to_text
from validate import validate_input, validate_output
from agent import convert

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
    report = validate_output(result, expected_count, schema, text)

    # Metrics print on every run — success or failure — so a failed run
    # tells us how far off the output was.
    print("Accuracy metrics:")
    for name, value in report["metrics"].items():
        print(f"  {name}: {value}")
    json.dump(report, open("report.json", "w"), indent=2, ensure_ascii=False)

    if report["errors"]:
        print("Output validation failed:")
        for e in report["errors"]:
            print(f"  - {e}")
        sys.exit(1)

    json.dump(result, open("output.json", "w"), indent=2, ensure_ascii=False)
    print(f"OK: wrote {len(result)} records to output.json")

if __name__ == "__main__":
    main()
