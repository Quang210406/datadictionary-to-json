"""Cut one document into the pieces a model is actually asked to read.

## Why this exists, in numbers

Measured from `.cache/`, before any of this was written:

    largest input ever sent          17,190 chars   (a hop spec, 65 records)
    largest reply, TRUNCATION seen   15,474 chars   (one .sql, 177 records)
    docling of the 138-page design doc          211,648 chars

That is twelve times anything this program has ever sent, against a file
thirteen times smaller that already truncated. A document cannot be one call.
The measured density on SQL is roughly one record per 87 characters; even a
tenth of that across 211k characters is several hundred records, and the
completeness check cannot save us because a document states no anchor — nothing
in a design document says how many field definitions it ought to contain.

## Why this does not weaken the governing principle

"AI reads files, Python joins them" is about what a single call may SEE, and the
point of it is that a value can be checked against the one place it came from
while a cross-file link cannot be hallucinated. Cutting a file into sections
moves in the safe direction on both counts: a call now sees strictly less, and
the evidence gets finer — `assemble._entry`'s `doc_link`, which is None on every
record this program has ever emitted, finally has something true to hold.

Two mechanical consequences fall out for free, and they are the reason to cut
here rather than inside the reader:

  * **The section id goes in the `sheet` slot.** `store.records(path, sheet,
    kind)` then works unchanged, cache keys stay `kind|sha|section`, and each
    section gets its own row in `store.reports` and so its own line in the
    completeness report. `RecordStore.records`' signature is untouched — the
    desktop app subclasses it to implement Stop.
  * **A failed section costs one section**, not a document. The store already
    records a failure and continues.
"""

import re

# Comfortably under the 15,474-char file that truncated, with room for the
# ~1,176-token fixed overhead per call. Chunking costs 5-16% more tokens
# overall; that is the price of a reply that arrives whole.
MAX_CHARS = 12000

# Below this a section is merged forward instead of being sent on its own. A
# heading with two lines under it is not worth a call, and validate.py rejects
# anything under 200 characters as too little to be a document at all.
MIN_CHARS = 400

# A markdown heading, or the page marker `readers._read_pypdf` inserts. Both are
# real boundaries: docling emits the first, pypdf the second, and a document
# read by either should cut at the places its reader actually marked.
BOUNDARY = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$|^---\s*trang\s+(\d+)\s*---\s*$",
                      re.I)

# A markdown table row, and the `|---|:--:|` rule beneath a header row.
TABLE_ROW = re.compile(r"^\s*\|")
TABLE_RULE = re.compile(r"^\s*\|[\s|:-]+\|?\s*$")

# The cache key is `kind|sha|section`, split on "|" by RecordStore._migrate, so
# a section id may not contain one.
_UNSAFE = re.compile(r"[|\r\n\t]+")


def _label(text, index) -> str:
    """A stable, readable id for one section.

    Stable matters more than pretty: this is a cache key, so an id that moved
    between runs would re-pay for every section on every run. It is derived from
    the section's ORDINAL and its heading, both of which are fixed by the text —
    and the text is already content-hashed into the same key.
    """
    clean = _UNSAFE.sub(" ", (text or "").strip())
    clean = re.sub(r"\s+", " ", clean)[:60].strip()
    return f"s{index:03d} {clean}" if clean else f"s{index:03d}"


def _table_header(lines, start) -> list:
    """The header rows of the table beginning at `start`, if it has any.

    Repeated at the top of every slice of an oversized table. A data-dictionary
    PDF's field listing is routinely one table of several hundred rows, and a
    slice of it with no header is a grid of unlabelled cells — the model would
    have to guess which column held the field name, which is exactly the kind of
    guess this program refuses to let it make.
    """
    if start + 1 < len(lines) and TABLE_RULE.match(lines[start + 1]):
        return [lines[start], lines[start + 1]]
    return []


def _cut(block, header=()) -> list:
    """One oversized block, cut at line boundaries and never mid-row.

    A table is cut between rows, with its header repeated, rather than being
    allowed to straddle a boundary. Everything else is cut between lines.
    """
    parts, current, size = [], list(header), sum(len(h) + 1 for h in header)
    for line in block:
        if size + len(line) + 1 > MAX_CHARS and len(current) > len(header):
            parts.append("\n".join(current))
            current = list(header)
            size = sum(len(h) + 1 for h in header)
        current.append(line)
        size += len(line) + 1
    if len(current) > len(header):
        parts.append("\n".join(current))
    return parts


def _split_block(lines) -> list:
    """One section's lines into one or more pieces of at most MAX_CHARS.

    Walks the block as an alternation of table runs and prose runs, so a cut
    never lands inside a table: prose is cut freely, a table is cut between its
    rows with its header carried over.
    """
    if sum(len(line) + 1 for line in lines) <= MAX_CHARS:
        return ["\n".join(lines)]

    pieces, i = [], 0
    while i < len(lines):
        if TABLE_ROW.match(lines[i]):
            start = i
            while i < len(lines) and TABLE_ROW.match(lines[i]):
                i += 1
            run = lines[start:i]
            header = _table_header(lines, start)
            body = run[len(header):]
            pieces += _cut(body, header) if body else ["\n".join(run)]
        else:
            start = i
            while i < len(lines) and not TABLE_ROW.match(lines[i]):
                i += 1
            pieces += _cut(lines[start:i])
    return [p for p in pieces if p.strip()]


def split(text) -> list:
    """[(section id, section text)] for one document.

    A document with no headings and no page markers comes back as one section
    when it is small, and as evenly cut pieces when it is not — the cut still
    respects tables. A document that is already small enough comes back as a
    single section whose id is "s000", so the common case costs nothing.
    """
    if not text or not text.strip():
        return []

    lines = text.splitlines()
    blocks, current, heading, headings = [], [], None, []
    for line in lines:
        match = BOUNDARY.match(line)
        if match and current:
            blocks.append(current)
            headings.append(heading)
            current, heading = [], None
        if match:
            heading = (match.group(2) or f"trang {match.group(3)}").strip()
        current.append(line)
    if current:
        blocks.append(current)
        headings.append(heading)

    # Merge a block too small to be worth its own call into the one before it,
    # so a run of bare headings does not become a run of near-empty calls.
    merged, merged_headings = [], []
    for block, head in zip(blocks, headings):
        size = sum(len(line) + 1 for line in block)
        if merged and size < MIN_CHARS and \
                sum(len(l) + 1 for l in merged[-1]) + size <= MAX_CHARS:
            merged[-1] += block
        else:
            merged.append(list(block))
            merged_headings.append(head)

    out = []
    for block, head in zip(merged, merged_headings):
        for piece in _split_block(block):
            if piece.strip():
                out.append((_label(head, len(out)), piece))
    return out


def describe(sections) -> dict:
    """What the split did, for the report."""
    sizes = [len(text) for _, text in sections]
    return {
        "sections": len(sections),
        "chars": sum(sizes),
        "largest_section": max(sizes, default=0),
        "over_limit": sum(1 for s in sizes if s > MAX_CHARS),
    }
