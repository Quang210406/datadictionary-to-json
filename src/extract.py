import pandas as pd

# Read one sheet as a raw grid: drop fully empty rows
def read_excel_df(path: str, sheet_name="Mapping") -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name, header=None)
    return df.dropna(how="all")

# Turn the raw grid into plain CSV text for the AI agent to read.
def df_to_text(df: pd.DataFrame) -> str:
    return df.to_csv(index=False, header=False)
