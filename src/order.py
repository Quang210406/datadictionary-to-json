"""Stage order, derived from the claims rather than declared in a config.

This is the part with no precedent in the codebase, and the reason the rewrite
is worth doing at all.

Of the seven `assemble._entry` call sites, five take their stage from the
archive layout, one is the literal `"source"`, and exactly one derives anything
(`kinds.get(kind).stage`, off the CREATE statement). So a `.sql` file states its
own stage, an Excel workbook borrows one from the folder it sits in, and prose
has nothing to borrow from at all. Adding a third format under the old scheme
meant inventing a third mechanism.

There is a better answer available, and it was always available: **the order is
implied by the claims themselves.** If one file says `DWH_X` is loaded from
`STG_Y` and another says `STG_Y` is loaded from `SRC_Z`, then the order
SRC -> STG -> DWH is a fact about the corpus, not a configuration of it. Nobody
has to declare it and — the part that matters — nobody can declare it *wrong*.

That closes the one hole nothing in this program currently checks. A wrong stage
ORDER passes fidelity (every value really is in its file), passes completeness
(every row really did produce a record) and produces a confidently wrong
pipeline. No single file can catch it, because the error is not in any single
file. A derived order can be compared against the declared one, and this module
is what makes that comparison possible.

**It does not replace the declared names.** `compare.py` keys every archive row
on `dwh_table`/`dwh_column` and lays its columns out by stage position, so
renaming `dwh` to `stage_2` would score zero for reasons that have nothing to do
with lineage. So where a layout exists its names still label the stages, and the
derived order AUDITS them. Derived labels are for a corpus that never had a
layout — which, until now, was every corpus this program could not read.
"""

from dataclasses import dataclass
from typing import List, Optional

from assemble import table_key

# A pipeline deeper than this is a cycle nobody has noticed, or a corpus this
# was not designed for. `assemble.MAX_DEPTH` is 8 for the same reason and the
# two are deliberately the same number: a chain the walker refuses to follow
# past 8 hops should not be described as having 9 stages.
MAX_POSITIONS = 8


@dataclass(frozen=True)
class Order:
    """What the claims say the pipeline's shape is."""

    # positions[i] is the set of table keys whose longest path from an origin
    # is i. Index IS the stage position.
    positions: List[set]
    depths: dict                # table key -> position
    back_edges: List[tuple]     # (source, subject) dropped to break a cycle
    edges: int                  # distinct edges considered

    @property
    def count(self) -> int:
        return len(self.positions)


def edges_of(claims) -> set:
    """Distinct (source table, subject table) pairs the claims assert.

    Self-edges are dropped rather than reported: a table loaded from itself is
    how an incremental reload is written, it is extremely common, and it says
    nothing about ORDER. Keeping it would make every such table its own
    predecessor and force it a position deeper than it belongs.
    """
    out = set()
    for claim in claims:
        source, subject = table_key(claim.source_table), table_key(claim.subject_table)
        if source and subject and source != subject:
            out.add((source, subject))
    return out


def derive(claims) -> Order:
    """The positions the claims imply, deepest path wins.

    Longest path rather than shortest, deliberately. A field that skips a stage
    — loaded into the warehouse straight from source, which real archives do —
    would under a shortest-path rule drag the whole warehouse up beside staging
    and collapse two stages into one. The longest path is the number of hops the
    corpus can actually demonstrate, which is the honest answer to "how deep is
    this pipeline".
    """
    edges = edges_of(claims)
    preds = {}
    nodes = set()
    for source, subject in edges:
        preds.setdefault(subject, set()).add(source)
        nodes.add(source)
        nodes.add(subject)

    depths, back_edges = {}, []
    # Iterative depth-first, so a deep corpus cannot blow the Python stack and
    # so the cycle guard is a plain set rather than call-stack state.
    WALKING, DONE = 0, 1
    state = {}

    for start in sorted(nodes):
        if start in state:
            continue
        stack = [(start, iter(sorted(preds.get(start, ()))))]
        state[start] = WALKING
        while stack:
            node, pending = stack[-1]
            advanced = False
            for parent in pending:
                if state.get(parent) == WALKING:
                    # A back edge: this parent is still open further down the
                    # stack, so following it would loop. Recorded, never
                    # resolved — which of the two directions is "wrong" is a
                    # question about the platform, not about the text.
                    back_edges.append((parent, node))
                    continue
                if parent not in state:
                    state[parent] = WALKING
                    stack.append((parent, iter(sorted(preds.get(parent, ())))))
                    advanced = True
                    break
            if advanced:
                continue
            # Every parent resolved: this node's depth is one past the deepest.
            parents = [p for p in preds.get(node, ())
                       if state.get(p) == DONE and p in depths]
            depths[node] = min(1 + max((depths[p] for p in parents), default=-1),
                               MAX_POSITIONS - 1)
            state[node] = DONE
            stack.pop()

    span = max(depths.values(), default=-1) + 1
    positions = [set() for _ in range(span)]
    for node, depth in depths.items():
        positions[depth].add(node)
    return Order(positions=positions, depths=depths,
                 back_edges=sorted(set(back_edges)), edges=len(edges))


def _common_prefix(names) -> Optional[str]:
    """The prefix every name at one position shares, if it is a real one.

    `STG_MDM_PARTY` and `STG_TXN_HISTORY` share `STG_`; that is a stage name
    somebody already chose and it beats anything this module could invent. Two
    unrelated names share nothing and the caller falls back to a position
    number. A prefix is only believed at an underscore, so `CUSTOMER` and
    `CUST_ID` do not yield `CUST`.
    """
    names = sorted(n for n in names if n)
    if len(names) < 2:
        return None
    first, last = names[0], names[-1]
    size = 0
    while size < min(len(first), len(last)) and first[size] == last[size]:
        size += 1
    prefix = first[:size]
    return prefix[:prefix.rindex("_")] if "_" in prefix else None


def stage_names(order: Order, declared=None) -> List[str]:
    """A name per position.

    With a declared layout the declared names win — see the module docstring;
    `compare.py` and every hand-built ground truth are written in them, and a
    derivation that renamed them would be measuring a different thing. Without
    one, names come from the tables themselves, and fall back to positional
    labels that are ugly on purpose: `stage_2` says "nobody declared this",
    which is the truth and should look like it.
    """
    if declared:
        return list(declared[:order.count]) + [
            f"stage_{i}" for i in range(len(declared), order.count)]

    names = []
    for i, tables in enumerate(order.positions):
        if i == 0:
            # Position 0 is produced by nothing in the corpus, which is what
            # "source" has always meant here (assemble.SOURCE_STAGE).
            names.append("source")
            continue
        prefix = _common_prefix(tables)
        names.append(prefix.lower() if prefix else f"stage_{i}")
    return names


def audit(order: Order, declared_pairs, declared_stages) -> dict:
    """Does the derived order agree with the one the layout declares?

    `declared_pairs` is [(subject table, the stage its FILE was filed under)] —
    for the archive that is the hop folder's `to_stage`, stamped on by
    `catalog.build_catalog`. So this compares two independent answers to the
    same question: the folder a workbook sits in, and the shape of the graph its
    contents describe. Nothing has ever compared them.

    Disagreement is REPORTED, not raised. A table can legitimately be loaded at
    two depths, and only somebody who knows the platform can say whether a
    mismatch is a mis-filed workbook or a real skip-level load.
    """
    by_position, conflicts = {}, []
    for table, stage in declared_pairs:
        key = table_key(table)
        if key is None or key not in order.depths or not stage:
            continue
        by_position.setdefault(order.depths[key], {}).setdefault(stage, set()).add(key)

    derived = []
    for position in sorted(by_position):
        stages = by_position[position]
        # The declared stage most tables at this position agree on. A position
        # whose tables disagree is exactly the finding worth surfacing.
        winner = max(stages, key=lambda s: (len(stages[s]), s))
        derived.append(winner)
        for stage, tables in stages.items():
            if stage != winner:
                conflicts.append({
                    "position": position, "declared": stage,
                    "majority": winner,
                    "tables": sorted(tables)[:5], "count": len(tables)})

    expected = [s for s in (declared_stages or []) if s in set(derived)]
    return {
        "derived_positions": order.count,
        "declared_stages": list(declared_stages or []),
        "derived_order": derived,
        # The declared list filtered to the stages that actually appear as a
        # produced stage. An archive declares four and its hop folders produce
        # two of them: `source` is nobody's target and `cloud` comes from the
        # reference workbook, which states no mapping claim and so contributes
        # no edge. That is a property of the corpus, not a disagreement.
        "declared_order_of_produced": expected,
        "agrees": derived == expected,
        "conflicts": conflicts[:5],
        "conflict_count": len(conflicts),
        "cycles_broken": len(order.back_edges),
        "cycle_examples": [f"{a} -> {b}" for a, b in order.back_edges[:5]],
        "edges": order.edges,
        "tables": len(order.depths),
    }
