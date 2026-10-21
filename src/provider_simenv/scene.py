"""Scene metadata shared with the static exporter, without reading measurements."""

from pathlib import Path

from .agents import Transport
from .export_bundle import (
    HONESTY_NOTE,
    _collapsed_edges,
    _entity_metadata,
    _node_metadata,
)
from .topology import build_flow_adjacency, build_roster


def build_scene(pdl_path: Path) -> dict:
    roster = build_roster(pdl_path)
    entities = _entity_metadata(pdl_path)
    transports = {
        entry.archetype.name for entry in roster
        if entry.archetype.agent_class is Transport and not entry.entity_ids
    }
    nodes = [_node_metadata(entry, entities) for entry in roster
             if entry.archetype.name not in transports]
    return {
        "schema_version": 1, "pdl": pdl_path.name,
        "honesty_note": HONESTY_NOTE, "nodes": nodes,
        "edges": _collapsed_edges(
            build_flow_adjacency(pdl_path), transports,
            {node["id"] for node in nodes},
        ),
    }
