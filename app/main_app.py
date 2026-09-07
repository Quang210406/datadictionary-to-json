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
import descriptions                   # noqa: E402  (path set by runner)
import emit                           # noqa: E402
import survey                         # noqa: E402
from assemble import target_entry, target_key  # noqa: E402

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

    def open_results(self):
        """Load a results folder an earlier run wrote.

        Until this existed, results lived only in memory and only for as long
        as the window stayed open: closing it made a finished run unreachable,
        even though the folder was still on disk. For someone who reads output
        that somebody else produced, that was the whole app being unusable.

        The output.json check is not defensive padding. read_results() returns
        empty structures for a folder with nothing in it, so without the check
        an empty or wrong folder renders as a SUCCESSFUL run of zero records —
        a clean, confident, entirely false screen.
        """
        picked = webview.create_file_dialog(webview.FOLDER_DIALOG)
        if not picked:
            return {"ok": False}
        out_dir = Path(picked[0])
        if not (out_dir / "output.json").exists():
            return {"ok": False, "error": "no_results", "folder": out_dir.name}

        result = {"ok": True, "out_dir": str(out_dir),
                  **runner.read_results(out_dir)}
        self._state["result"] = result
        # The same summary shape start()'s on_done sends, because the page
        # renders both through the same runFinished handler.
        summary = {k: v for k, v in result.items() if k != "records"}
        summary["record_count"] = len(result.get("records") or [])
        self._emit("runFinished", summary)
        return {"ok": True}

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
            # The entry target_key CHOSE, not the end of the chain. Those are
            # different for 19 of 83 records in the real archive: a chain that
            # reaches the cloud copy ends there, but the field is named by its
            # warehouse entry — and the cloud sheet files tables without the
            # warehouse prefix, so the two are literally different names
            # (TXN_HISTORY.ID vs DWH_TXN_HISTORY.ID, say).
            #
            # Showing one while counting siblings by the other made the window
            # disagree with itself. It also disagrees with the description
            # template, which keys on target_key — a reviewer comparing the
            # two would see two names for one field and reasonably file a bug.
            named = target_entry(record) or chain[-1]
            rows.append({
                "i": index,
                "table": named.get("table") or "",
                "column": named.get("column") or "",
                "stage": named.get("stage") or "",
                "datatype": _datatype(named),
                "description": record.get("description") or "",
                # Kept in its own column, never merged into the one above: one
                # is copied from a document and checkable against it, the other
                # is somebody's reading, and a single column holding both would
                # make that difference unrecoverable for the next reader.
                "authored": descriptions.authored_for(
                    record, self._state.get("overlay")) or "",
                "stages": len(chain),
                "siblings": siblings.get(target_key(record), 1),
            })

        if query:
            needle = query.strip().upper()
            rows = [r for r in rows
                    if needle in r["table"].upper()
                    or needle in r["column"].upper()
                    or needle in r["description"].upper()
                    or needle in r["authored"].upper()]

        return {"total": len(rows), "rows": rows[offset:offset + limit]}

    def field_detail(self, index):
        """The full chain for one record, with the evidence file per stage."""
        records = (self._state.get("result") or {}).get("records") or []
        if not 0 <= index < len(records):
            return {"ok": False}
        return {"ok": True, "record": records[index]}

    # -- descriptions -----------------------------------------------------
    #
    # These two exist because this app is handed over. Both operations were
    # command-line only, which meant the person filling descriptions in could
    # neither produce the sheet nor put it back — every loop ran through
    # whoever still had a terminal. That is fine while that person is around.

    def export_descriptions(self):
        """Write the description sheet for the run currently on screen.

        Into the run's own dated folder, so the sheet and the dictionary it
        describes stay together and cannot be mistaken for another run's.
        """
        result = self._state.get("result") or {}
        records = result.get("records") or []
        if not records:
            return {"ok": False, "error": "no_results"}
        out_dir = Path(result.get("out_dir") or runner.OUTPUT_ROOT)
        stages = (result.get("report", {}).get("chain_diagnostics")
                  or {}).get("stages") or []
        try:
            path, count = descriptions.export_template(
                records, out_dir / "mo_ta.xlsx", stages,
                self._state.get("prefill"))
        except ValueError as exc:
            return {"ok": False, "error": "refused", "detail": str(exc)}
        return {"ok": True, "path": str(path), "fields": count}

    def load_descriptions(self):
        """Read a filled-in sheet and join it into this run.

        The text never enters output.json: that file means what the documents
        state, and a sentence somebody wrote cannot be checked against a
        source the way every other value in it can. It is joined into the
        spreadsheet and shown in the table, which is where a person reads it.
        """
        result = self._state.get("result") or {}
        records = result.get("records") or []
        if not records:
            return {"ok": False, "error": "no_results"}
        picked = webview.create_file_dialog(
            webview.OPEN_DIALOG, file_types=("Excel (*.xlsx)",))
        if not picked:
            return {"ok": False}

        stages = (result.get("report", {}).get("chain_diagnostics")
                  or {}).get("stages") or []
        try:
            overlay = descriptions.load(picked[0], stages)
        except ValueError as exc:
            # The layout guard fires here: a sheet written against a different
            # archive keys its fields differently, so every row would orphan.
            return {"ok": False, "error": "wrong_file", "detail": str(exc)}

        report = descriptions.merge_report(records, overlay)
        self._state["overlay"] = overlay
        result.setdefault("report", {})["descriptions"] = report

        # Rewrite the spreadsheet with the extra column. Archive layout only —
        # the SQL workbook has no description column yet.
        rewritten = False
        out_dir = Path(result.get("out_dir") or "")
        if out_dir.is_dir() and result.get("report", {}).get("mode") != "sql":
            try:
                emit.write_workbook(records, str(out_dir / "output.xlsx"),
                                    None, overlay)
                rewritten = True
            except Exception:
                rewritten = False
        return {"ok": True, "rewrote_xlsx": rewritten, **report}

    def descriptions_from_documents(self):
        """Pick a folder of prose documents and pre-fill the description sheet.

        Costs API calls, so it runs on a thread and reports through the same
        logLine bridge a run uses. The result is a PRE-FILL, not an answer: the
        meanings land in the column a person writes in, each naming the document
        and section it came from, so a reviewer edits or deletes them exactly
        like their own text.
        """
        result = self._state.get("result") or {}
        records = result.get("records") or []
        if not records:
            return {"ok": False, "error": "no_results"}
        picked = webview.create_file_dialog(webview.FOLDER_DIALOG)
        if not picked:
            return {"ok": False}

        def on_line(line):
            self._emit("logLine", line)

        def on_done(outcome):
            if outcome.get("ok"):
                # Kept for export_descriptions to use; never written into
                # output.json, which means only what the documents state.
                self._state["prefill"] = outcome.get("prefill") or {}
            self._emit("docsFinished",
                       {k: v for k, v in outcome.items() if k != "prefill"})

        runner.read_documents_async(records, picked[0], on_line, on_done)
        return {"ok": True, "started": True}

    # -- settings ---------------------------------------------------------

    def key_status(self):
        """Which API key is in play. Never returns the key itself."""
        return runner.key_status()

    def save_settings(self, provider=None, model=None, key=None):
        """Change provider, model or key. Never returns a key back to the page."""
        return runner.save_settings(provider, model, key)

    def propose_layout(self, folder):
        """Survey a folder this program has no layout for, and propose one.

        Reads folder and sheet names only, never a cell, so it costs nothing
        and is safe on a folder nobody understands yet. The proposal is
        returned for a person to read; accepting it is a separate step.
        """
        try:
            facts = survey.survey(folder)
            proposal = survey.propose(facts)
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        # Saved beside the cache, not into the surveyed folder — that folder
        # may be read-only, and writing into someone's data uninvited is not
        # this program's business.
        target = runner.SUPPORT_ROOT / "layouts" / (Path(folder).name + ".json")
        survey.write_proposal(proposal, target)
        return {"ok": True, "path": str(target),
                "text": survey.render(facts, proposal),
                "warnings": proposal["warnings"]}

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
