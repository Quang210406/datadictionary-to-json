"""How a file becomes text the agent can read — one entry per format.

Until now the program could read exactly two things: a spreadsheet, via pandas,
and a `.sql` file, via `Path.read_text`. Both were hard-wired into
`store._read_source`, chosen by the source kind's `reader` flag. Point the tool
at a PDF and nothing happened — not an error, just a file nobody looked at. The
archive it was written against contains **four** such PDFs, one of them a
138-page database design document.

So the reader becomes a registry, in the same pattern as `kinds.py` and
`providers.py`: declared once, checked at import, and asked at run time what it
can actually do. Adding a format is one entry here rather than a new branch in
the middle of the store.

**Two readers may claim the same extension, and the better one wins.** `pypdf`
extracts a PDF's text layer — 0.4 MB, no models, no network. `docling` does
that and understands layout, tables and scans, at the cost of torch and a model
download on first use. So docling is declared with a higher priority and is
simply *used instead* the moment it is installed. Nothing here changes when it
arrives; the registry notices.

That ordering is the whole design. It means the program is not betting on which
library wins — a format is a slot, and whichever reader is present fills it.

What no reader can fix: a PDF that is a photograph of a page has no text to
extract, and `pypdf` returns nothing rather than guessing. One of the four is
exactly that. It is reported, not silently skipped, because a document nobody
can read is a fact about the archive that somebody should know.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Tuple

# How much text a page must yield before we believe the file has a text layer
# at all. A scanned page still "extracts" a handful of stray characters from
# stamps and page numbers, so zero is the wrong threshold.
MIN_CHARS_PER_PAGE = 40


@dataclass(frozen=True)
class Reader:
    """One way of turning a file into text.

    `probe` answers whether this reader can run in THIS install — a reader
    whose package is missing is declared but unavailable, never crashed on.
    Priority breaks ties: higher wins, so a better reader supersedes a simpler
    one by being installed rather than by anyone editing this file.
    """

    name: str
    label: str
    extensions: Tuple[str, ...]
    priority: int
    probe: Callable[[], bool]
    read: Callable[[str], str]


# ---------------------------------------------------------------- plain text

def _probe_text():
    return True


def _read_text(path):
    return Path(path).read_text(errors="ignore")


# ---------------------------------------------------------------- pypdf

def _probe_pypdf():
    try:
        import pypdf            # noqa: F401
        return True
    except Exception:
        return False


def _read_pypdf(path):
    """The PDF's text layer, page by page.

    Pages are separated by a marker rather than run together: the agent is
    asked to copy values verbatim, and a value split across a page break would
    otherwise be silently welded to the next page's first word.
    """
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "") for page in reader.pages]
    body = "\n\n".join(f"--- trang {i} ---\n{text}"
                       for i, text in enumerate(pages, start=1) if text.strip())
    if len(body) < MIN_CHARS_PER_PAGE * max(len(pages), 1):
        raise NoTextLayer(
            f"{Path(path).name}: {len(pages)} page(s) yielded "
            f"{len(body)} characters. This is almost certainly a scan — an "
            "image of a page, with no text to extract. Reading it needs OCR, "
            "which this build does not have.")
    return body


# ---------------------------------------------------------------- docling

def _probe_docling():
    try:
        from docling.document_converter import DocumentConverter   # noqa: F401
        return True
    except Exception:
        return False


def _read_docling(path):
    """Layout-aware text, when docling is installed.

    Preferred over pypdf wherever both apply: it keeps table structure and
    heading hierarchy, which is exactly the "which section did this come from"
    that a rules document needs, and it can OCR a scan. It is not a hard
    dependency because it pulls torch and fetches model weights on first use —
    a runtime download on someone else's machine is a poor thing to put in a
    handover.
    """
    from docling.document_converter import DocumentConverter
    return DocumentConverter().convert(str(path)).document.export_to_markdown()


class NoTextLayer(ValueError):
    """The file is readable, but there is nothing in it to read."""


_REGISTRY = (
    Reader(name="text", label="plain text", extensions=(".sql", ".txt", ".md"),
           priority=0, probe=_probe_text, read=_read_text),
    Reader(name="pypdf", label="PDF (text layer)", extensions=(".pdf",),
           priority=10, probe=_probe_pypdf, read=_read_pypdf),
    Reader(name="docling", label="PDF/Word/PowerPoint (layout-aware)",
           extensions=(".pdf", ".docx", ".pptx", ".html", ".md"),
           priority=50, probe=_probe_docling, read=_read_docling),
)

READERS = {r.name: r for r in _REGISTRY}


def for_path(path):
    """The best available reader for this file, or None.

    Sorted by priority so installing a better reader is the whole upgrade —
    no edit here, no flag to set.
    """
    suffix = Path(path).suffix.lower()
    candidates = [r for r in _REGISTRY
                  if suffix in r.extensions and r.probe()]
    return max(candidates, key=lambda r: r.priority) if candidates else None


def read(path) -> str:
    """The file as text, using whichever reader is best and present."""
    reader = for_path(path)
    if reader is None:
        raise ValueError(
            f"No reader for {Path(path).suffix or 'this file'}. "
            f"Readable here: {sorted(readable_extensions())}.")
    return reader.read(path)


def readable_extensions() -> set:
    """Every extension some INSTALLED reader can handle."""
    return {ext for r in _REGISTRY if r.probe() for ext in r.extensions}


def describe() -> list:
    """What this build can actually read — for the report and the UI."""
    return [{"name": r.name, "label": r.label,
             "extensions": list(r.extensions), "available": r.probe()}
            for r in sorted(_REGISTRY, key=lambda r: -r.priority)]


def _check():
    """Reject a half-declared reader at import."""
    if len(READERS) != len(_REGISTRY):
        raise ValueError("two readers share a name")
    for reader in _REGISTRY:
        if not reader.name or not reader.label:
            raise ValueError(f"reader {reader.name!r} is missing a name or label")
        if not reader.extensions:
            raise ValueError(
                f"reader {reader.name!r} claims no extensions, so for_path "
                "could never select it — it would be dead code that looks live.")
        for ext in reader.extensions:
            if not ext.startswith(".") or ext != ext.lower():
                raise ValueError(
                    f"reader {reader.name!r} extension {ext!r} must be "
                    "lower-case and start with a dot; for_path lower-cases the "
                    "suffix before matching, so anything else never matches.")


_check()
