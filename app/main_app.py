"""The desktop window.

pywebview gives a real macOS window whose contents are HTML — a native title
bar and native file dialogs, with a layout engine good enough to render a
lineage table and Vietnamese text properly. This module is only the bridge:
every method on Api is callable from JavaScript as `pywebview.api.<name>()`,
and nothing about the extraction lives here.
"""

import json
import subprocess
import sys
import webbrowser
from pathlib import Path

import webview

import runner
# Imported after runner, which is what puts src/ on sys.path. The n-1 badges
# below count target fields, and this is the same rule validate.py's coverage
# metrics count by — shared rather than copied, so the window and the report
# cannot disagree about what "a target field" is.
from assemble import target_key      # noqa: E402  (path set by runner above)

WEB_DIR = runner.BUNDLE / "app" / "web"


class Api:
    """The whole surface JavaScript can reach. Deliberately small."""

    def __init__(self):
        self.window = None
        self._state = {}

    # -- picking ----------------------------------------------------------

    def choose_folder(self):
        result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return {"ok": False}
        return {"ok": True, "folder": result[0]}

    def scan(self, folder, layout_path=None):
        """Index the folder. No AI, no quota, safe to repeat."""
        return runner.scan(folder, layout_path)

    def choose_layout(self):
        """Pick an archive.json describing a differently-shaped archive.

        The CLI has --layout for this; without the same reach the window can
        only open archives shaped like the one the program was written
        against, which is the opposite of the point.
        """
        result = self.window.create_file_dialog(
            webview.OPEN_DIALOG, file_types=("Layout (*.json)",))
        if not result:
            return {"ok": False}
        return {"ok": True, "path": result[0]}

    # -- running ----------------------------------------------------------

    def start(self, mode, folder, selected, layout_path=None):
        """Kick off a run and return immediately.

        Progress arrives in the page through logLine(); the finished result
        through runFinished(). Doing it this way keeps the window responsive
        during what can be several minutes of API calls.
        """
        def on_line(line):
            self._emit("logLine", line)

        def on_done(result):
            self._state["result"] = result
            # Records can be tens of megabytes. Only the summary crosses the
            # bridge on completion; rows are fetched a page at a time below.
            summary = {k: v for k, v in result.items() if k != "records"}
            summary["record_count"] = len(result.get("records") or [])
            self._emit("runFinished", summary)

        runner.run_async(mode, folder, selected, on_line, on_done, layout_path)
        return {"ok": True}

    def stop(self):
        """Ask the run to stop. It lands after the file in flight finishes —
        see the note in runner.py for why that is the granularity."""
        runner.request_stop()
        return {"ok": True}

    # -- results ----------------------------------------------------------

    def fields(self, query="", offset=0, limit=200):
        """One page of the dictionary, flattened for the table.

        Each row is one record — one (target field, source field) pair, which
        is what the tool actually emits. Collapsing them to one row per target
        field would hide the n-1 cases, and those are the ones most worth
        checking by eye.
        """
        records = (self._state.get("result") or {}).get("records") or []

        # How many records share each target field. A field fed by several
        # sources exists as several records, so this count IS the n-1 signal
        # — not the number of source entries in one chain, which is just the
        # number of hops.
        siblings = {}
        for record in records:
            key = target_key(record)
            if key:
                siblings[key] = siblings.get(key, 0) + 1

        rows = []
        for index, record in enumerate(records):
            chain = record.get("lineage") or []
            if not chain:
                continue
            last = chain[-1]
            rows.append({
                "i": index,
                "table": last.get("table") or "",
                "column": last.get("column") or "",
                "stage": last.get("stage") or "",
                "datatype": _datatype(last),
                "description": record.get("description") or "",
                "stages": len(chain),
                "siblings": siblings.get(target_key(record), 1),
            })

        if query:
            needle = query.strip().upper()
            rows = [r for r in rows
                    if needle in r["table"].upper()
                    or needle in r["column"].upper()
                    or needle in r["description"].upper()]

        return {"total": len(rows), "rows": rows[offset:offset + limit]}

    def field_detail(self, index):
        """The full chain for one record, with the evidence file per stage."""
        records = (self._state.get("result") or {}).get("records") or []
        if not 0 <= index < len(records):
            return {"ok": False}
        return {"ok": True, "record": records[index]}

    # -- files ------------------------------------------------------------

    def reveal(self, path):
        """Show a file or folder in Finder — the app's only 'export' step."""
        target = Path(path)
        if not target.exists():
            return {"ok": False}
        subprocess.run(["open", "-R", str(target)] if target.is_file()
                       else ["open", str(target)], check=False)
        return {"ok": True}

    def open_file(self, path):
        """Open with whatever the Mac uses for that type — .xlsx to Excel."""
        if not Path(path).exists():
            return {"ok": False}
        subprocess.run(["open", str(path)], check=False)
        return {"ok": True}

    # -- internal ---------------------------------------------------------

    def _emit(self, fn, payload):
        if self.window is None:
            return
        try:
            self.window.evaluate_js(f"window.{fn} && window.{fn}({json.dumps(payload)})")
        except Exception:
            pass                                # window closed mid-run


def _datatype(entry):
    datatype, size = entry.get("datatype"), entry.get("size")
    if datatype and size:
        return f"{datatype}({size})"
    return datatype or ""


def launch():
    api = Api()
    window = webview.create_window(
        "Hecate",
        str(WEB_DIR / "index.html"),
        js_api=api,
        width=1180, height=800,
        min_size=(940, 640),
    )
    api.window = window
    webview.start()


if __name__ == "__main__":
    launch()
