"""Look at a folder and say what is in it — then, separately, guess its shape.

`catalog.build_catalog` only ever opens the folders a layout names. Point the
tool at an archive it has no layout for and it reports "no hop specs found",
which is true and useless: the folder is full of workbooks and nothing says
what it saw. Someone who cannot hand-write JSON is stuck there.

This module fixes that, in two halves that are deliberately not the same kind
of thing:

    survey()   FACTS. Which subfolders, how many workbooks in each, which
               table each workbook describes, which files look like a
               final-stage workbook, which table-name prefixes occur. Every
               line of it can be checked by opening the folder.

    propose()  A GUESS, labelled as one, with the evidence for each part
               written beside it.

**A proposal is never applied.** It is written out for a person to read and
accept. That restraint is the whole reason this is safe to have: a wrong stage
ORDER would pass fidelity (every value still appears in its source file) and
pass completeness (every row still produced a record) and emit a confidently
wrong pipeline. It would be the first claim in this system that nothing can
check. Reporting cannot cause that; inferring silently can.

Costs nothing. It reads directory entries and workbook sheet NAMES — never a
cell — so no API call, no quota, and it is safe to run on a folder nobody
understands yet.
"""

import json
import re
from collections import Counter
from pathlib import Path

from catalog import tables_of
from layout import LayoutError, validate_layout

# Folder-name tokens that conventionally mean a pipeline stage. Used only to
# make a proposal readable — "STGDIH" is a real folder token, "staging" is what
# a person calls it. Every mapping is stated in the evidence so a reader can
# reject it. An unrecognised token is kept verbatim rather than guessed at.
STAGE_ALIASES = {
    "SRC": "source", "SOURCE": "source", "RAW": "source",
    "STG": "staging", "STGDIH": "staging", "STAGING": "staging",
    "DWH": "dwh", "DWHDIH": "dwh", "WAREHOUSE": "dwh",
    "ODS": "ods", "MART": "mart", "CLOUD": "cloud",
}

CLOUD_HINTS = ("CLOUD", "MAPPING")
TABLE_PREFIX = re.compile(r"^([A-Z]+_)")


def _sheet_names(path):
    """Sheet names only. Deliberately not cell contents."""
    try:
        from openpyxl import load_workbook
        return load_workbook(path, read_only=True).sheetnames
    except Exception:
        return []


def survey(archive_dir, non_hop_sheets=("DDL",)) -> dict:
    """What is actually in this folder. No guessing, no judgement."""
    root = Path(archive_dir)
    skip = {s.strip().upper() for s in non_hop_sheets}
    folders, prefixes = [], Counter()

    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        books = [p for p in sorted(child.glob("*.xlsx"))
                 if not p.name.startswith("~$")]
        tables = []
        for book in books:
            # EVERY hop sheet, not just the first. A workbook holding several
            # table sheets would otherwise be reported as holding one, and the
            # survey's whole job is to say what is actually there.
            for table, _ in tables_of(book, skip):
                if not table:
                    continue
                tables.append(table)
                match = TABLE_PREFIX.match(table)
                if match:
                    prefixes[match.group(1)] += 1
        folders.append({
            "dir": child.name,
            "workbooks": len(books),
            "tables": tables,
            "prefixes": dict(Counter(TABLE_PREFIX.match(t).group(1)
                                     for t in tables
                                     if TABLE_PREFIX.match(t))),
        })

    loose = [p for p in sorted(root.glob("*.xlsx"))
             if not p.name.startswith("~$")]
    cloud_candidates = [
        {"file": p.name, "sheets": len(_sheet_names(p))}
        for p in loose
        if any(hint in p.name.upper() for hint in CLOUD_HINTS)
    ]

    return {
        "root": str(root),
        "folders": folders,
        "loose_workbooks": [p.name for p in loose],
        "cloud_candidates": cloud_candidates,
        "table_prefixes": dict(prefixes),
    }


def _splits(name):
    """Every way a folder name could be read as <FROM>_<TO>."""
    parts = name.split("_")
    return [("_".join(parts[:i]), "_".join(parts[i:]))
            for i in range(1, len(parts))]


def _chain(edges):
    """Order the stages if these (from, to) edges form one simple path."""
    froms = [a for a, _ in edges]
    tos = [b for _, b in edges]
    starts = [a for a in froms if a not in tos]
    if len(starts) != 1:
        return None
    order, seen, node = [starts[0]], {starts[0]}, starts[0]
    forward = dict(edges)
    if len(forward) != len(edges):
        return None                      # a stage feeding two places: not a path
    while node in forward:
        node = forward[node]
        if node in seen:
            return None                  # a cycle
        seen.add(node)
        order.append(node)
    return order if len(order) == len(edges) + 1 else None


def propose(facts) -> dict:
    """A candidate layout, plus why each part of it was guessed.

    The folder-name convention `<FROM>_<TO>` gives the hops. Which underscore
    to split on is not assumed — every split is tried, and the reading kept is
    the one whose edges chain into a single path. That is a derivation the
    folder names corroborate, not a preference.
    """
    named = [f for f in facts["folders"] if f["workbooks"]]
    evidence, warnings = [], []

    options = {f["dir"]: _splits(f["dir"]) for f in named}
    unsplittable = [d for d, s in options.items() if not s]
    for d in unsplittable:
        warnings.append(
            f"folder {d!r} has no underscore, so it cannot be read as "
            "<FROM>_<TO>; left out of the proposal")
    options = {d: s for d, s in options.items() if s}

    chosen, order = None, None
    for combo in _combinations(options):
        candidate = _chain(list(combo.values()))
        if candidate:
            chosen, order = combo, candidate
            break

    if chosen is None:
        # Fall back to folder ORDER: each folder is taken to write into a stage
        # named after itself, reading from the one before it. That is a usable
        # pipeline rather than a pile of disconnected pairs — but it is a guess
        # about sequence made from nothing but alphabetical order, so it is
        # warned about in the strongest terms available.
        warnings.append(
            "the folder names do not chain into one pipeline, so the ORDER "
            "below is nothing but the alphabetical order of the folders. This "
            "is the part no single file can check: a wrong order still passes "
            "every check this program has and produces a confidently wrong "
            "pipeline. Read it before accepting it.")
        first = "source"
        chosen, previous = {}, first
        for folder in named:
            chosen[folder["dir"]] = (previous, folder["dir"])
            previous = folder["dir"]
        order = [first] + [f["dir"] for f in named]
    else:
        evidence.append(
            "hop order derived from the folder names: "
            + " -> ".join(order)
            + ". Each folder was read as <FROM>_<TO> and the readings chain "
              "into a single path, which is what corroborates the split.")

    stages = [STAGE_ALIASES.get(token.upper(), token.lower()) for token in order]
    renamed = [f"{t} -> {s}" for t, s in zip(order, stages)
               if t.upper() in STAGE_ALIASES]
    if renamed:
        evidence.append("folder tokens renamed by convention: "
                        + ", ".join(renamed) + ". Edit if wrong.")

    stage_of = dict(zip(order, stages))
    hops = [{"dir": d, "from": stage_of[a], "to": stage_of[b]}
            for d, (a, b) in chosen.items()]
    # In PIPELINE order, not the order the folders happened to be scanned in.
    # `layout.final_hop_dir` reads hops[-1] to decide which tables a run builds
    # by default, so an alphabetically-ordered list makes the program build the
    # tables written by the FIRST hop — the wrong end of the pipeline. The
    # prose above already states the right order; only the JSON disagreed, and
    # the symptom is a run that reports 0% complete chains for no visible
    # reason.
    hops.sort(key=lambda h: stages.index(h["from"]) if h["from"] in stages
              else len(stages))

    # Corroboration: the tables in a folder should carry the prefix of the
    # stage it writes INTO. Reported, never used to override the names.
    for hop in hops:
        found = next((f for f in named if f["dir"] == hop["dir"]), None)
        if found and found["prefixes"]:
            top = max(found["prefixes"], key=found["prefixes"].get)
            evidence.append(
                f"{hop['dir']}: tables mostly named {top}* "
                f"({found['prefixes'][top]} of {len(found['tables'])}), "
                f"consistent with it writing into {hop['to']!r}")

    layout = {"stages": stages, "hops": hops, "non_hop_sheets": ["DDL"]}

    if facts["cloud_candidates"]:
        pick = facts["cloud_candidates"][0]
        layout["stages"] = stages + ["cloud"]
        layout["cloud"] = {"glob": pick["file"], "stage": "cloud",
                           "table_prefixes": sorted(facts["table_prefixes"])}
        evidence.append(
            f"final-stage workbook guessed as {pick['file']!r} "
            f"({pick['sheets']} sheets) because its name looks like one. "
            "If that is wrong, delete the whole \"cloud\" block.")
    elif facts["loose_workbooks"]:
        warnings.append(
            f"{len(facts['loose_workbooks'])} workbook(s) sit loose in the "
            "root and none looks like a final-stage file; no cloud stage "
            "proposed")

    try:
        validate_layout(layout)
        valid = True
    except LayoutError as exc:
        valid, _ = False, warnings.append(f"the proposal does not validate: {exc}")

    return {"layout": layout, "evidence": evidence, "warnings": warnings,
            "valid": valid}


def _combinations(options):
    """Every way of choosing one split per folder, fewest-splits-first."""
    dirs = list(options)
    if not dirs:
        return [{}]
    out = [{}]
    for name in dirs:
        out = [dict(partial, **{name: split})
               for partial in out for split in options[name]]
    return out


def render(facts, proposal) -> str:
    """The whole thing as text, facts first, guess second and labelled."""
    lines = [f"Surveyed: {facts['root']}", "",
             "WHAT IS THERE (facts — open the folder and check):"]
    for folder in facts["folders"]:
        lines.append(f"  {folder['dir']}/  {folder['workbooks']} workbook(s)"
                     + (f", tables like {', '.join(folder['tables'][:3])}"
                        if folder["tables"] else ""))
    if facts["loose_workbooks"]:
        lines.append(f"  (root)  {len(facts['loose_workbooks'])} loose "
                     f"workbook(s): {', '.join(facts['loose_workbooks'][:3])}")
    if facts["table_prefixes"]:
        lines.append(f"  table prefixes seen: {facts['table_prefixes']}")

    lines += ["", "PROPOSED LAYOUT (a guess — nothing is applied):"]
    for line in proposal["evidence"]:
        lines.append(f"  - {line}")
    for line in proposal["warnings"]:
        lines.append(f"  ! {line}")
    lines += ["", json.dumps(proposal["layout"], indent=2, ensure_ascii=False)]
    return "\n".join(lines)


def write_proposal(proposal, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(proposal["layout"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return path
