"""Deterministic assembly: walk a field backwards through the archive.

This mirrors exactly how the reference dictionary was built by hand:

    open the file that OWNS the target table
    read the row -> it names a source table and column
    look that source table up in the catalog
    open the file that owns IT, read its row for that column
    repeat until no file owns the table -> that is the origin
    finally look the target up in the cloud workbook

No AI here. The records come from the store; everything below is dict
lookups, so a wrong result can be blamed on extraction or on this file, but
never on both at once.
"""

from copy import deepcopy

from catalog import build_catalog

MAX_DEPTH = 8  # guards against a table that (transitively) sources itself


def _normalize(value):
    """Trim and case-fold one half of a key. FOR MATCHING ONLY — never
    written to an output record, so the dictionary still reports the source's
    own spelling, padding and all."""
    return value.strip().upper() if isinstance(value, str) else None


def field_key(table, column):
    """The single definition of "the same field"; every match uses it."""
    normalized_column = _normalize(column)
    if not normalized_column:
        return None
    return (_normalize(table), normalized_column)


def stages_in(records) -> list:
    """The stage names present, in pipeline order, read off the records.

    Emit, compare and the coverage metrics all need to know the stages. Taking
    them from the data rather than a constant means they work on any archive
    shape without being told what it is. The longest chain gives the order,
    since a record missing an early stage would otherwise mislead about it.
    """
    order = []
    for record in sorted(records, key=lambda r: -len(r.get("lineage", []))):
        for entry in record.get("lineage", []):
            if entry["stage"] not in order:
                order.append(entry["stage"])
    return order


def format_key(key) -> str:
    table, column = key
    return f"{table}.{column}" if table else column


def _entry(stage, table, column, datatype, size, path, sources, schema=None) -> dict:
    return {
        "stage": stage,
        "schema": schema,
        "table": table,
        "column": column,
        "datatype": datatype,
        "size": size,
        "constraint": None,
        # The file this stage's facts were read from — the "Đường dẫn"
        # column of the hand-built dictionary, and the evidence trail the
        # BRD calls "Cơ sở xác định".
        "doc_link": None,
        "offline_path": path,
        "sources": sources,
    }


def _source_of(record) -> dict:
    return {
        "table": record.get("source_table"),
        "column": record.get("source_column"),
        "transformation_type": record.get("transformation_type"),
        "transformation_logic": record.get("transformation_logic"),
        "role": record.get("source_role") or "value",
    }


def _cloud_lookup(cloud_index, table, column, prefixes=()):
    """Cloud detail for a warehouse field.

    The cloud workbook files some tables without the warehouse prefix
    (DWH_FDM_TRAN_HIS is on a sheet called FDM_TRAN_HIS) and others with it,
    so try each configured prefix stripped before giving up.
    """
    names = [table]
    normalized = _normalize(table) or ""
    for prefix in prefixes:
        if normalized.startswith(prefix.upper()):
            names.append(table[len(prefix):])
    for name in names:
        detail = cloud_index.get(field_key(name, column))
        if detail:
            return detail
    return None


def _rows_for(store, entry, kind="hop_spec"):
    return store.records(entry["path"], entry["sheet"], kind)


def _match(records, column):
    """Every record in this file whose TARGET is that column (n-1 gives
    several)."""
    want = _normalize(column)
    return [r for r in records if _normalize(r.get("target_column")) == want]


def _walk_back(table, column, catalog, store, depth, seen):
    """Entries upstream of (table, column), nearest stage last.

    Returns [] when no file owns the table — the chain has reached its
    origin and the caller records the stated source as the first stage.
    """
    key = field_key(table, column)
    if depth >= MAX_DEPTH or key is None or key in seen:
        return []
    owner = catalog.get(_normalize(table))
    if owner is None:
        return []
    seen = seen | {key}

    matches = _match(_rows_for(store, owner), column)
    if not matches:
        return []
    # The sheet name is authoritative for the table it describes. The per-row
    # "Target Table Name" cell is often the SOURCE table copied down the
    # column (STG_FDM_TRAN_HIS.xlsx labels every row "FDM_TRAN_HIS"), and
    # trusting it breaks the chain at the next hop.
    owner_table = (owner.get("sheet") or "").strip() or table
    # Upstream of a field, take the first mapping. A fan-in further back is
    # real but it turns the chain into a tree; current scope keeps the
    # nearest source line and the diagnostics report the rest.
    record = matches[0]
    src_stage, tgt_stage = owner["from_stage"], owner["to_stage"]

    entry = _entry(tgt_stage, owner_table, column,
                   record.get("target_datatype"), record.get("target_size"),
                   owner["path"], [_source_of(record)])

    upstream = _walk_back(record.get("source_table"), record.get("source_column"),
                          catalog, store, depth + 1, seen)
    if not upstream and record.get("source_column"):
        upstream = [_entry(src_stage, record.get("source_table"),
                           record.get("source_column"), record.get("source_datatype"),
                           record.get("source_size"), owner["path"], [])]
    return upstream + [entry]


def resolve_table(target_table, catalog, store, cloud_index=None,
                  cloud_stage="cloud", table_prefixes=()) -> list:
    """One lineage record per (target field, source field) of one table.

    The stage names come from the catalog entry, which the layout stamped on
    when the archive was indexed; nothing here knows a folder name.
    """
    owner = catalog.get(_normalize(target_table))
    if owner is None:
        return []
    src_stage, tgt_stage = owner["from_stage"], owner["to_stage"]
    cloud_index = cloud_index or {}

    # Same rule as _walk_back: the sheet names the table, not the row cell.
    owner_table = (owner.get("sheet") or "").strip() or target_table
    out = []
    for record in _rows_for(store, owner):
        column = record.get("target_column")
        if not column:
            continue
        table = owner_table

        entry = _entry(tgt_stage, table, column, record.get("target_datatype"),
                       record.get("target_size"), owner["path"],
                       [_source_of(record)])

        upstream = _walk_back(record.get("source_table"), record.get("source_column"),
                              catalog, store, 1, {field_key(table, column)})
        if not upstream and record.get("source_column"):
            upstream = [_entry(src_stage, record.get("source_table"),
                               record.get("source_column"),
                               record.get("source_datatype"),
                               record.get("source_size"), owner["path"], [])]

        lineage = upstream + [entry]

        detail = _cloud_lookup(cloud_index, table, column, table_prefixes)
        if detail:
            lineage.append(_entry(cloud_stage, detail.get("table"), detail.get("column"),
                                  detail.get("datatype"), detail.get("size"),
                                  detail.get("path"), []))
            lineage[-1]["constraint"] = detail.get("nullable")

        out.append({
            "description": (detail or {}).get("description"),
            "lineage": lineage,
        })
    return out


def build_cloud_index(cloud_path, sheets, store) -> dict:
    """{(TABLE, COLUMN) -> cloud detail} across every per-table sheet."""
    index = {}
    for table, sheet in sheets.items():
        for record in store.records(cloud_path, sheet, "cloud_sheet"):
            key = field_key(record.get("table") or table, record.get("column"))
            if key is not None:
                index.setdefault(key, {**record, "path": cloud_path})
    return index


# ------------------------------------------------------------ SQL views
#
# A view's whole lineage lives in one file, so there is no catalog to walk:
# one record is one (declared column, source field) pair, two stages deep.
# Where a view reads another view, chain_views() below adds the resolved
# origin as a separate field rather than lengthening the chain, so the record
# shape stays the same whether or not the upstream view was available.

VIEW_STAGES = ["source", "view"]
MAX_VIEW_DEPTH = 5


def _view_source(record) -> dict:
    return {
        "schema": record.get("source_schema"),
        "table": record.get("source_table"),
        "column": record.get("source_column"),
        "alias": record.get("source_alias"),
        "transformation_type": None,
        "transformation_logic": record.get("transformation_logic"),
        "role": record.get("source_role") or "value",
    }


def resolve_view(path, store) -> list:
    """One lineage record per (view column, source field) of one .sql file."""
    out = []
    for record in store.records(path, None, "view_sql"):
        column = record.get("target_column")
        if not column:
            continue
        source = _view_source(record)

        lineage = []
        if source["column"] or source["table"]:
            lineage.append(_entry("source", source["table"], source["column"],
                                  None, None, path, [], source["schema"]))

        lineage.append(_entry("view", record.get("target_table"), column,
                              None, None, path, [source]))

        out.append({"description": None, "lineage": lineage})
    return out


def _view_field(record):
    """(VIEW, COLUMN) this record produces."""
    for entry in record["lineage"]:
        if entry["stage"] == "view":
            return field_key(entry["table"], entry["column"])
    return None


def chain_views(view_records) -> list:
    """Follow sources that are themselves views, to their physical origin.

    Recorded as `resolved_source` rather than extra lineage stages: the
    extraction asserts one hop, which is what the ground truth scores and what
    fidelity can verify against a single file. Following the hop is a separate,
    deterministic step, and when the upstream view is missing the record simply
    keeps no resolved_source.
    """
    produced = {}
    for record in view_records:
        key = _view_field(record)
        if key is not None:
            produced.setdefault(key, record)

    merged = deepcopy(view_records)
    for record in merged:
        source = record["lineage"][0]
        if source["stage"] != "source":
            continue
        via, seen = [], set()
        table, column = source["table"], source["column"]
        for _ in range(MAX_VIEW_DEPTH):
            key = field_key(table, column)
            if key is None or key in seen or key not in produced:
                break
            seen.add(key)
            via.append(format_key(key))
            upstream = produced[key]["lineage"][0]
            if upstream["stage"] != "source":
                break
            table, column = upstream["table"], upstream["column"]
        if via:
            record["resolved_source"] = {
                "schema": None, "table": table, "column": column,
                "via": via,
            }
    return merged
