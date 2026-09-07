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


# Where a key the USER supplies is kept. Deliberately outside the bundle: a
# key baked at build time belongs to whoever built it, and this app is being
# handed to someone who will still be using it after that person has gone.
# Without somewhere to put her own key, a working tool would one day stop and
# nobody left would be able to fix it.
SUPPORT_ROOT = Path.home() / "Library" / "Application Support" / "Hecate"
USER_KEY_FILE = SUPPORT_ROOT / "api_key.txt"      # the older, Gemini-only form
SETTINGS_FILE = SUPPORT_ROOT / "settings.json"


def _read_settings():
    """{provider, model, keys{}} — with the old key file folded in.

    An earlier build stored one bare Gemini key in api_key.txt. Reading it here
    means somebody who already saved a key keeps working after an update rather
    than silently falling back to the bundled one and wondering why their quota
    is being used.
    """
    data = {}
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    keys = dict(data.get("keys") or {})
    legacy = ""
    try:
        legacy = USER_KEY_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    if legacy and "gemini" not in keys:
        keys["gemini"] = legacy
    return {"provider": data.get("provider") or "", 
            "model": data.get("model") or "", "keys": keys}


def _write_settings(settings):
    SUPPORT_ROOT.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    SETTINGS_FILE.chmod(0o600)


def _bundled_key():
    try:
        from app import bundled_key            # generated at build time
        return bundled_key.GEMINI_API_KEY
    except Exception:
        try:
            import bundled_key                 # frozen: top-level module
            return bundled_key.GEMINI_API_KEY
        except Exception:
            return ""


def user_key(provider="gemini"):
    """A key the user saved for this provider, or "" if they never did."""
    return (_read_settings()["keys"].get(provider) or "").strip()


def save_settings(provider=None, model=None, key=None):
    """Change provider, model, or this provider's key. Any subset.

    A key of "" clears that provider's key rather than storing an empty one,
    which is how someone reverts to the key built into the app.
    """
    settings = _read_settings()
    if provider is not None:
        settings["provider"] = (provider or "").strip().lower()
    if model is not None:
        settings["model"] = (model or "").strip()
    if key is not None:
        target = settings["provider"] or "gemini"
        key = key.strip()
        if key:
            settings["keys"][target] = key
        else:
            settings["keys"].pop(target, None)
            # Also drop the legacy file, or it would keep resurrecting.
            if target == "gemini" and USER_KEY_FILE.exists():
                USER_KEY_FILE.unlink()
    _write_settings(settings)
    _prepare_environment(force=True)
    return key_status()


def key_status():
    """What settings are in play, without ever handing a key back.

    Only the last four characters cross the bridge — enough to tell two keys
    apart when checking which is active, useless to anyone reading over a
    shoulder or scrolling a log.
    """
    import providers
    settings = _read_settings()
    active_name = settings["provider"] or providers.DEFAULT_PROVIDER
    try:
        provider = providers.get(active_name)
    except ValueError:
        provider = providers.get(providers.DEFAULT_PROVIDER)

    own = (settings["keys"].get(provider.name) or "").strip()
    bundled = _bundled_key() if provider.name == providers.DEFAULT_PROVIDER else ""
    active = own or bundled
    return {
        **providers.describe(),
        "has_key": bool(active) or provider.key_var is None,
        "source": "own" if own else ("bundled" if bundled else "none"),
        "tail": active[-4:] if active else "",
    }


# Provider -> the environment variable its SDK reads. Declared here rather than
# imported from providers.py because this runs BEFORE src/ is importable.
_KEY_VARS = {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY",
             "anthropic": "ANTHROPIC_API_KEY", "mistral": "MISTRAL_API_KEY"}


def _prepare_environment(force=False):
    """Put the API key in the environment before agent.py is imported.

    agent.py calls load_dotenv() at import time and then reads
    os.environ["GEMINI_API_KEY"]. python-dotenv does not overwrite variables
    that are already set, so setting it here wins, and the same module works
    unmodified whether it is run from the CLI (.env) or the app (baked key).

    The user's own key beats the baked one. `force` is for the moment she
    saves a new key mid-session — without it the already-set variable would
    keep the old value and the change would appear to do nothing until relaunch.

    The bundled key is Gemini's alone. A key baked at build time belongs to
    whoever built it; extending it to a provider they never configured would
    mean silently sending documents somewhere nobody chose.
    """
    settings = _read_settings()
    if settings["provider"] and (force or not os.environ.get("HECATE_PROVIDER")):
        os.environ["HECATE_PROVIDER"] = settings["provider"]
    if settings["model"] and (force or not os.environ.get("HECATE_MODEL")):
        os.environ["HECATE_MODEL"] = settings["model"]

    for name, key in settings["keys"].items():
        var = _KEY_VARS.get(name)
        if var and key and (force or not os.environ.get(var)):
            os.environ[var] = key.strip()

    baked = _bundled_key()
    if baked and not os.environ.get("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = baked


_prepare_environment()

import main as cli                             # noqa: E402  (path set above)
import layout as layout_mod                    # noqa: E402
import readers as readers_mod                  # noqa: E402
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


def _readable_documents(root):
    """Document filenames under `root`, relative, in a stable order.

    The same filter build_docs uses: a reader must exist for the extension, and
    .sql/.txt are excluded because those are the other two modes' territory.
    Which extensions qualify depends on what is INSTALLED — a bundle without
    docling sees PDFs only — so the caller passes the list on to the window
    rather than naming formats the build may not have.
    """
    found = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("~$"):
            continue
        if path.suffix.lower() in (".sql", ".txt"):
            continue
        if readers_mod.for_path(path):
            found.append(str(path.relative_to(root)))
    return found


def _unreadable_documents(root):
    """[(name, suffix)] for files some reader CLAIMS but none can open here.

    Only extensions the registry knows about, so a folder of images or zips is
    still just a folder with nothing in it — the answer there is "this is not
    an archive", not "install something".
    """
    declared = {ext for reader in readers_mod.describe()
                for ext in reader["extensions"]}
    out = []
    for path in sorted(root.rglob("*")):
        suffix = path.suffix.lower()
        if (path.is_file() and not path.name.startswith("~$")
                and suffix in declared and suffix not in (".sql", ".txt")
                and not readers_mod.for_path(path)):
            out.append((str(path.relative_to(root)), suffix))
    return out


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
        # No hop workbooks — but a folder of PDFs or Word files is now a
        # dictionary this program can build, so look before reporting a
        # failure. Checked AFTER the archive, deliberately: a real archive
        # often contains prose documents too (this project's own has four
        # PDFs), and a folder that is both should be read as the archive it is.
        docs = _readable_documents(root)
        if docs:
            return {"ok": True, "mode": "docs", "folder": str(root),
                    "items": docs, "label": "documents",
                    "readable": sorted(readers_mod.readable_extensions())}

        # Documents are there, but THIS build cannot open them. Worth its own
        # answer: the small bundle ships with pypdf only, so a folder of Word
        # or PowerPoint files lands here, and reporting it as a bad archive
        # layout sends someone looking for a config file that would not help.
        # Naming the formats and the reason is the difference between "this is
        # broken" and "this build does not include that reader".
        unreadable = _unreadable_documents(root)
        if unreadable:
            return {"ok": False, "error": "no_reader",
                    "found_types": sorted({s for _, s in unreadable}),
                    "examples": [n for n, _ in unreadable[:5]],
                    "count": len(unreadable),
                    "readable": sorted(readers_mod.readable_extensions())}

        # Report what is actually there, not only what was expected. The old
        # message named this project's own folder names, which tells someone
        # holding a different archive nothing they can act on.
        present = sorted(p.name for p in root.iterdir()
                         if p.is_dir() and not p.name.startswith("."))
        return {"ok": False, "needs_layout": True,
                "expected_dirs": [h["dir"] for h in archive_layout["hops"]],
                "found_dirs": present,
                "readable": sorted(readers_mod.readable_extensions()),
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

    if mode == "docs":
        # Its own cache, like the other two: a document extraction keyed
        # beside the hop specs would make either one harder to ship alone.
        args.cache = str(CACHE_ROOT / "docs.json")
        if selected and len(selected) < len(_readable_documents(Path(folder))):
            # Same staging trick the SQL branch uses, for the same reason: the
            # CLI takes a folder or one file and has no way to name a subset,
            # and widening its interface to suit the window is exactly the
            # drift this module exists to avoid. Names are flattened because a
            # document may sit in a subfolder, and collisions get a counter —
            # two files called the same thing in different folders is normal.
            staged = Path(tempfile.mkdtemp(prefix="hecate_docs_"))
            used = set()
            for name in selected:
                source = Path(folder) / name
                flat = Path(name).name
                stem, suffix = Path(flat).stem, Path(flat).suffix
                n = 2
                while flat in used:
                    flat = f"{stem}_{n}{suffix}"
                    n += 1
                used.add(flat)
                os.symlink(source, staged / flat)
            args.docs = str(staged)
        else:
            args.docs = folder
    elif mode == "sql":
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
            **read_results(out_dir)}


def read_documents(records, folder, on_line):
    """Read prose documents for what they say a field MEANS. Blocking.

    The CLI's --from-docs, reachable from the window. It is a JOIN, not an
    extraction: the model reads ONE document and says "column X means Y, found
    in section Z", is never shown the dictionary, and matching those statements
    to real fields happens afterwards in Python — so it cannot be led into
    agreeing with a dictionary it was shown.

    Its own cache file, matching the CLI: document extractions are keyed by
    content like every other, but mixing a 138-page PDF in beside the hop specs
    makes either one harder to ship on its own.
    """
    import descriptions

    root = Path(folder)
    docs = ([p for p in sorted(root.rglob("*"))
             if p.is_file() and readers_mod.for_path(p)
             and p.suffix.lower() not in (".sql", ".txt")]
            if root.is_dir() else [root])
    if not docs:
        return {"ok": False, "error": "no_documents",
                "readable": sorted(readers_mod.readable_extensions())}

    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    store = StoppableStore(cli.load_schemas(),
                           cache_path=str(CACHE_ROOT / "documents.json"))
    _stop.clear()

    stream = _LineWriter(on_line)
    real_stdout, real_stderr = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = stream
    try:
        prefill, report = descriptions.from_documents(records, store, docs)
    except RunCancelled:
        return {"ok": False, "cancelled": True}
    except Exception as exc:                    # noqa: BLE001 — surfaced to the UI
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        stream.flush()
        sys.stdout, sys.stderr = real_stdout, real_stderr

    return {"ok": True, "prefill": prefill, "documents": len(docs), **report}


def read_documents_async(records, folder, on_line, on_done):
    thread = threading.Thread(
        target=lambda: on_done(read_documents(records, folder, on_line)),
        daemon=True)
    thread.start()
    return thread


def read_results(out_dir):
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
