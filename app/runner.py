"""Drives one extraction run, without changing anything in src/.

`main.run(args)` already exists as a seam: its docstring says it was split
from argument parsing "so the GUI can call it with the same options the
command line would produce". That is exactly how it is used here. Nothing in
src/ is patched, re-implemented, or imported differently — so if the CLI is
correct, this is correct, and the two cannot drift apart.

The GUI adds one step the CLI does not have: a *scan*, which indexes the
archive without calling the AI. It exists because the CLI's default (build
every table found) is a ninety-file, quota-consuming run that a tester should
never trigger by accident. Scanning is free; it lets a person see what is in
the folder and choose.
"""

import io
import json
import os
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

# --- Locating src/ and schemas/ -------------------------------------------
#
# Frozen and unfrozen layouts differ, and main.py computes its schema path
# from its own __file__ (ROOT = parent.parent). Inside a PyInstaller bundle
# that path does not survive, so the two directories are resolved here and
# main.SCHEMA_DIR is corrected after import. Everything else in src/ is
# path-independent.

if getattr(sys, "frozen", False):
    BUNDLE = Path(sys._MEIPASS)
else:
    BUNDLE = Path(__file__).resolve().parent.parent

SRC_DIR = BUNDLE / "src"
SCHEMA_DIR = BUNDLE / "schemas"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _prepare_environment():
    """Put the API key in the environment before agent.py is imported.

    agent.py calls load_dotenv() at import time and then reads
    os.environ["GEMINI_API_KEY"]. python-dotenv does not overwrite variables
    that are already set, so setting it here wins, and the same module works
    unmodified whether it is run from the CLI (.env) or the app (baked key).
    """
    try:
        from app import bundled_key            # generated at build time
        key = bundled_key.GEMINI_API_KEY
    except Exception:
        try:
            import bundled_key                 # frozen: top-level module
            key = bundled_key.GEMINI_API_KEY
        except Exception:
            key = ""
    if key and not os.environ.get("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = key


_prepare_environment()

import main as cli                             # noqa: E402  (path set above)
import layout as layout_mod                    # noqa: E402
from catalog import build_catalog              # noqa: E402
from store import RecordStore                  # noqa: E402

cli.SCHEMA_DIR = SCHEMA_DIR


# --- Stopping a run -------------------------------------------------------
#
# Nothing in src/ knows how to be cancelled, and it should not: a run is a
# straight line through the archive, and adding checkpoints along it would
# scatter GUI concerns through code the command line shares.
#
# There is exactly one place worth checking. RecordStore.records() is, in the
# README's words, "the whole interface between assembly and anything
# expensive" — every AI call, every workbook read, reaches it first. So the
# store is the thing made stoppable, by subclassing it here and rebinding the
# name main.py resolves. src/store.py is not edited and not patched; the run
# is simply handed a different store than the command line builds.
#
# Cancellation therefore lands BETWEEN files, never inside one. A file that
# is mid-conversion finishes, because interrupting an in-flight API call
# would mean paying for a reply and throwing it away. One file is the
# granularity, and the window says so rather than pretending it is instant.

_stop = threading.Event()


class RunCancelled(Exception):
    """Raised on the run thread when the window has asked it to stop."""


class StoppableStore(RecordStore):
    latest = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Kept so a cancelled run can still report how much it got through.
        StoppableStore.latest = self

    def records(self, path, sheet, kind):
        if _stop.is_set():
            raise RunCancelled()
        return super().records(path, sheet, kind)


cli.RecordStore = StoppableStore


def request_stop():
    """Ask the running extraction to stop. Safe to call when none is running."""
    _stop.set()


# --- Where the app keeps its files ----------------------------------------
#
# A bundled app starts with "/" as its working directory, so every path the
# CLI leaves relative has to be made absolute. Outputs go somewhere a
# non-technical person can find in Finder; the cache goes to Application
# Support because it is machine state, not a result — and because it holds
# verbatim text of the source documents, which should not sit in Documents.

OUTPUT_ROOT = Path.home() / "Documents" / "Hecate"
CACHE_ROOT = Path.home() / "Library" / "Application Support" / "Hecate" / "cache"


class _LineWriter(io.TextIOBase):
    """Turns the CLI's print() calls into callbacks, one whole line at a time."""

    def __init__(self, on_line):
        self._on_line = on_line
        self._buffer = ""

    def write(self, text):
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._on_line(line)
        return len(text)

    def flush(self):
        if self._buffer:
            self._on_line(self._buffer)
            self._buffer = ""


def scan(folder, layout_path=None):
    """Index a folder without calling the AI. Free, and always safe to run.

    Returns the mode it detected and what is available to build, so the UI
    can offer a choice instead of defaulting to "everything".

    `layout_path` is the GUI's equivalent of the CLI's --layout. Without it
    the app could only ever reach two of load_layout's three resolution
    paths, which meant an archive shaped differently from the one this was
    written against was simply unusable from the window, even though the
    program itself handles it fine.
    """
    root = Path(folder)
    if not root.is_dir():
        return {"ok": False, "error": f"Not a folder: {folder}"}

    sql_files = sorted(p.name for p in root.glob("*.sql"))
    if sql_files:
        return {"ok": True, "mode": "sql", "folder": str(root),
                "items": sql_files, "label": "view scripts"}

    try:
        archive_layout = layout_mod.load_layout(str(root), layout_path)
    except (layout_mod.LayoutError, ValueError) as exc:
        return {"ok": False, "error": f"Bad archive layout: {exc}",
                "needs_layout": True}

    catalog = build_catalog(str(root), archive_layout)
    if not catalog:
        # Report what is actually there, not only what was expected. The old
        # message named this project's own folder names, which tells someone
        # holding a different archive nothing they can act on.
        present = sorted(p.name for p in root.iterdir()
                         if p.is_dir() and not p.name.startswith("."))
        return {"ok": False, "needs_layout": True,
                "expected_dirs": [h["dir"] for h in archive_layout["hops"]],
                "found_dirs": present,
                "used_layout": bool(layout_path)
                               or (root / layout_mod.CONFIG_NAME).exists()}

    # The CLI's default target set: tables produced by the last hop.
    last_dir = layout_mod.final_hop_dir(archive_layout)
    targets = sorted(t for t, v in catalog.items() if v["stage_dir"] == last_dir)
    return {"ok": True, "mode": "archive", "folder": str(root),
            "items": targets, "label": "target tables",
            "indexed": len(catalog), "stages": archive_layout["stages"],
            "layout_path": layout_path}


def _run_folder(source_folder):
    """One dated folder per run, named after the input, so runs never
    overwrite each other and two runs can be compared side by side.

    Seconds are in the name, and a counter is appended if that still
    collides. Stamping only to the minute meant two runs started within the
    same minute — which is exactly what happens when someone stops a run and
    immediately retries — silently shared a folder, and the second overwrote
    the first's dictionary.
    """
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    name = Path(source_folder).name.replace(" ", "_") or "run"
    folder = OUTPUT_ROOT / f"{name}_{stamp}"
    suffix = 2
    while folder.exists():
        folder = OUTPUT_ROOT / f"{name}_{stamp}_{suffix}"
        suffix += 1
    folder.mkdir(parents=True)
    return folder


def run(mode, folder, selected, on_line, layout_path=None):
    """Execute one extraction. Blocking — callers run it on a thread.

    `selected` is the list of tables (archive) or view filenames (sql) the
    person ticked. An empty list means everything, matching the CLI.
    """
    out_dir = _run_folder(folder)
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)

    # Built to mirror parse_args() exactly, including every default, so the
    # run is identical to the command line it corresponds to.
    args = cli.parse_args([])
    args.out = str(out_dir / "output.json")
    args.xlsx = str(out_dir / "output.xlsx")
    args.report = str(out_dir / "report.json")

    if mode == "sql":
        args.cache = str(CACHE_ROOT / "views.json")
        if len(selected) == 1:
            args.sql = str(Path(folder) / selected[0])
        elif selected:
            # The CLI takes a whole folder or one file, with no way to name a
            # subset. Rather than widen its interface, the chosen files are
            # linked into a scratch folder and that folder is passed instead.
            #
            # It goes in a temp directory, not the results folder: what she
            # opens in Finder afterwards should hold the dictionary and
            # nothing else. The links keep their .sql suffix because
            # build_views() finds files by globbing "*.sql" — a link named
            # without it would be silently skipped and the run would report
            # no files at all.
            staged = Path(tempfile.mkdtemp(prefix="hecate_sql_"))
            for name in selected:
                source = Path(folder) / name
                link = staged / (name if name.endswith(".sql") else name + ".sql")
                os.symlink(source, link)
            args.sql = str(staged)
        else:
            args.sql = folder
    else:
        args.cache = str(CACHE_ROOT / "records.json")
        args.archive = folder
        args.table = list(selected)
        args.layout = layout_path      # same field parse_args() would set

    _stop.clear()
    StoppableStore.latest = None

    stream = _LineWriter(on_line)
    real_stdout, real_stderr = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = stream
    try:
        cli.run(args)
    except RunCancelled:
        # cli.run never reached finish(), so no dictionary was written — a
        # half-built one would be worse than none. The extraction itself is
        # not lost: the store flushes its cache after every file it converts,
        # so running again picks up where this stopped and re-pays for
        # nothing.
        stream.flush()
        store = StoppableStore.latest
        # Nothing was written into it, so do not leave a dated empty folder
        # behind for her to wonder about.
        try:
            out_dir.rmdir()
        except OSError:
            pass
        return {"ok": False, "cancelled": True,
                "files_done": len(store.reports) if store else 0,
                "files_converted": store.converted if store else 0}
    except SystemExit as exc:
        # run() calls sys.exit(1) for bad input. That must not kill the app.
        stream.flush()
        if exc.code:
            return {"ok": False, "error": "The run stopped. See the log above.",
                    "out_dir": str(out_dir)}
    except Exception as exc:                    # noqa: BLE001 — surfaced to the UI
        stream.flush()
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "out_dir": str(out_dir)}
    finally:
        stream.flush()
        sys.stdout, sys.stderr = real_stdout, real_stderr

    return {"ok": True, "out_dir": str(out_dir),
            **_read_results(out_dir)}


def _read_results(out_dir):
    """Read back exactly the files that were written.

    The UI deliberately shows the written artefacts rather than an in-memory
    copy, so what she reviews on screen is what she would send on.
    """
    def load(name):
        path = out_dir / name
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    return {"records": load("output.json") or [], "report": load("report.json") or {}}


def run_async(mode, folder, selected, on_line, on_done, layout_path=None):
    thread = threading.Thread(
        target=lambda: on_done(run(mode, folder, selected, on_line, layout_path)),
        daemon=True)
    thread.start()
    return thread
