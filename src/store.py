"""Extract + convert one workbook at a time, on demand, and remember it.

Resolving a chain visits files as it discovers them, so the whole archive is
never converted up front: a run touches only the tables it actually reaches.
Results are cached on disk by (path, sheet, mtime), so re-running after a
code change costs nothing and a person can iterate on the assembly logic
without paying for the same extraction twice.

Everything AI-shaped lives here. Assembly asks this store for records and
gets plain dicts back, so the join logic stays deterministic and testable.
"""

import json
from pathlib import Path

from agent import convert
from extract import (read_excel_df, df_to_text, expected_row_count,
                     read_sql_text, expected_column_count)
from validate import validate_input, validate_sql_input, validate_output

# Which reader turns a source file into the text the agent sees. A spreadsheet
# has to be flattened into CSV; a .sql file already is text. Each returns
# (text, expected_count, checkpoint-1 errors), so records() below is the same
# for every kind.
EXCEL_KINDS = ("hop_spec", "cloud_sheet")


def _read_source(path, sheet, kind):
    if kind in EXCEL_KINDS:
        df = read_excel_df(path, sheet)
        return df_to_text(df), expected_row_count(df, kind), validate_input(df)
    text = read_sql_text(path)
    # A view's completeness anchor is its declared column list, not a row count.
    return text, expected_column_count(text), validate_sql_input(text)


class RecordStore:
    def __init__(self, schemas, cache_path=None, verbose=True):
        self.schemas = schemas
        self.cache_path = Path(cache_path) if cache_path else None
        self.verbose = verbose
        self.reports = []          # one per file actually converted
        self._memory = {}          # (path, sheet, kind) -> records
        self._disk = {}
        if self.cache_path and self.cache_path.exists():
            self._disk = json.loads(self.cache_path.read_text(encoding="utf-8"))

    def _key(self, path, sheet, kind):
        mtime = int(Path(path).stat().st_mtime)
        return f"{kind}|{path}|{sheet}|{mtime}"

    def records(self, path, sheet, kind) -> list:
        """Records for one sheet, converting it only the first time."""
        memo = (path, sheet, kind)
        if memo in self._memory:
            return self._memory[memo]

        key = self._key(path, sheet, kind)
        if key in self._disk:
            # Only the extraction is cached, never its verdict: the checks are
            # cheap, pure Python, and re-running them means a change to
            # validate.py takes effect without re-paying for extraction.
            cached = self._disk[key]
            records = cached["records"]
            report = validate_output(records, cached.get("expected_count"),
                                     self.schemas[kind], cached.get("text", ""))
            self._memory[memo] = records
            self.reports.append({"path": path, "sheet": sheet, "kind": kind,
                                 **report, "cached": True})
            return records

        text, expected, errors = _read_source(path, sheet, kind)
        if errors:
            # Checkpoint 1 failed: report it and treat the file as empty
            # rather than aborting a run that spans dozens of workbooks.
            report = {"path": path, "sheet": sheet, "kind": kind,
                      "errors": errors, "metrics": {}, "cached": False}
            self.reports.append(report)
            self._memory[memo] = []
            return []

        if self.verbose:
            label = f" [{sheet}]" if sheet else ""
            print(f"  converting {Path(path).name}{label} ({kind}) ...")
        schema = self.schemas[kind]
        try:
            records = convert(text, schema, kind)
        except Exception as exc:
            # A run spans dozens of files; one transient API failure or one
            # unparseable reply must not destroy the other 89. Record it as
            # an extraction problem, leave the table empty, and let the
            # report show exactly which files are missing and why.
            message = f"{type(exc).__name__}: {str(exc)[:200]}"
            if self.verbose:
                print(f"    FAILED - {message}")
            self.reports.append({"path": path, "sheet": sheet, "kind": kind,
                                 "errors": [f"extraction failed - {message}"],
                                 "metrics": {}, "cached": False})
            self._memory[memo] = []
            return []

        report = validate_output(records, expected, schema, text)
        report = {"path": path, "sheet": sheet, "kind": kind, **report}

        self.reports.append({**report, "cached": False})
        self._memory[memo] = records
        # The source text is kept so the fidelity check can re-run from cache.
        self._disk[key] = {"records": records, "text": text,
                           "expected_count": expected}
        self._flush()
        return records

    def _flush(self):
        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(self._disk, indent=1, ensure_ascii=False), encoding="utf-8"
            )

    @property
    def converted(self):
        return sum(1 for r in self.reports if not r.get("cached"))
