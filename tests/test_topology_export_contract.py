"""Contract between the shipped PDL derivation and the legacy export overlay."""
from pathlib import Path

from provider_simenv.tick_writer import AGENT_TABLES
from provider_simenv.topology import (
    FLOW_ADJACENCY,
    TRANSITIONAL_SEA,
    build_flow_adjacency,
    build_roster,
)
from fixtures.topology_snapshot_23 import EDGES_23, NODE_META_23, PORT_META_23


PDL = (
    Path(__file__).parents[1]
    / "src"
    / "provider_simenv"
    / "scenarios"
    / "s1-soja.pdl.yaml"
)

LANE_NAMES = frozenset(
    archetype.name for archetype in TRANSITIONAL_SEA.values()
)

EXPECTED_DERIVED_ONLY_NODES = {
    "sea_lane_santos": ((), False),
    "sea_lane_paranagua": ((), False),
    "sea_lane_arg": ((), False),
    "sea_lane_usa": ((), False),
}

EXPECTED_DERIVED_ONLY_EDGES = {
    (
        "transport_sa_santos->sea_lane_santos",
        "transport_sa_santos",
        "sea_lane_santos",
        True,
    ),
    (
        "sea_lane_santos->transport_eu_rtm",
        "sea_lane_santos",
        "transport_eu_rtm",
        True,
    ),
    (
        "transport_sa_paranagua->sea_lane_paranagua",
        "transport_sa_paranagua",
        "sea_lane_paranagua",
        True,
    ),
    (
        "sea_lane_paranagua->transport_eu_ham",
        "sea_lane_paranagua",
        "transport_eu_ham",
        True,
    ),
    (
        "wholesalers->sea_lane_arg",
        "wholesalers",
        "sea_lane_arg",
        True,
    ),
    (
        "sea_lane_arg->transport_eu_rtm",
        "sea_lane_arg",
        "transport_eu_rtm",
        True,
    ),
    (
        "wholesalers->sea_lane_usa",
        "wholesalers",
        "sea_lane_usa",
        True,
    ),
    (
        "sea_lane_usa->transport_eu_rtm",
        "sea_lane_usa",
        "transport_eu_rtm",
        True,
    ),
}

EXPECTED_HARDCODED_ONLY_EDGES = {
    (
        "transport_sa_santos->transport_eu_rtm",
        "transport_sa_santos",
        "transport_eu_rtm",
        True,
    ),
    (
        "transport_sa_paranagua->transport_eu_ham",
        "transport_sa_paranagua",
        "transport_eu_ham",
        True,
    ),
    (
        "arg_farmers->transport_eu_rtm",
        "arg_farmers",
        "transport_eu_rtm",
        True,
    ),
    (
        "usa_farmers->transport_eu_rtm",
        "usa_farmers",
        "transport_eu_rtm",
        True,
    ),
}


def _derived_nodes() -> dict[str, tuple[tuple[str, ...], bool]]:
    recorded_ids = {node_id for node_id, _ in AGENT_TABLES.values()}
    return {
        entry.archetype.name: (
            entry.entity_ids,
            entry.archetype.name in recorded_ids,
        )
        for entry in build_roster(PDL)
    }


def _hardcoded_nodes() -> dict[str, tuple[tuple[str, ...], bool]]:
    nodes = {
        node_id: (tuple(meta["entityIds"]), True)
        for node_id, meta in NODE_META_23.items()
    }
    nodes.update(
        {
            node_id: (tuple(meta["entityIds"]), False)
            for node_id, meta in PORT_META_23.items()
        }
    )
    return nodes


def _derived_edges(
    adjacency: dict[str, tuple[str, ...]],
) -> set[tuple[str, str, str, bool]]:
    return {
        (
            f"{source}->{target}",
            source,
            target,
            source in LANE_NAMES or target in LANE_NAMES,
        )
        for target, sources in adjacency.items()
        for source in sources
    }


def _hardcoded_edges() -> set[tuple[str, str, str, bool]]:
    return {
        (f"{source}->{target}", source, target, is_sea_crossing)
        for source, target, is_sea_crossing in EDGES_23
    }


def test_shipped_pdl_derivation_matches_the_documented_export_delta() -> None:
    adjacency = build_flow_adjacency(PDL)
    assert adjacency == FLOW_ADJACENCY

    derived_nodes = _derived_nodes()
    hardcoded_nodes = _hardcoded_nodes()
    common_node_ids = derived_nodes.keys() & hardcoded_nodes.keys()

    assert {
        node_id: derived_nodes[node_id]
        for node_id in derived_nodes.keys() - hardcoded_nodes.keys()
    } == EXPECTED_DERIVED_ONLY_NODES
    assert hardcoded_nodes.keys() - derived_nodes.keys() == set()
    assert {
        node_id: derived_nodes[node_id] for node_id in common_node_ids
    } == {
        node_id: hardcoded_nodes[node_id] for node_id in common_node_ids
    }

    derived_edges = _derived_edges(adjacency)
    hardcoded_edges = _hardcoded_edges()

    assert len({edge_id for edge_id, _, _, _ in derived_edges}) == len(derived_edges)
    assert len({edge_id for edge_id, _, _, _ in hardcoded_edges}) == len(
        hardcoded_edges
    )
    assert derived_edges - hardcoded_edges == EXPECTED_DERIVED_ONLY_EDGES
    assert hardcoded_edges - derived_edges == EXPECTED_HARDCODED_ONLY_EDGES


def test_topology_only_and_full_exports_emit_identical_graphs(
    tmp_path, monkeypatch
) -> None:
    import json
    import sys

    from provider_simenv import export_bundle

    agent_values = {
        prop: True if prop == "active" else 1.0
        for _, props in AGENT_TABLES.values()
        for prop in props
    }
    agent_frame = export_bundle.pd.DataFrame(
        [{"id_scenario": 1, "period": 0, **agent_values}]
    )
    env_frame = export_bundle.pd.DataFrame(
        [
            {
                "id_scenario": 1,
                "period": 0,
                **{csv_col: 1.0 for csv_col, _ in export_bundle.ENV_COLS},
            }
        ]
    )

    def read_csv(path: str):
        if str(path).endswith("Result_Simulator_Environment.csv"):
            return env_frame
        return agent_frame

    monkeypatch.setattr(export_bundle.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(export_bundle.pd, "read_csv", read_csv)
    full = export_bundle.build_bundle("unused", 1, str(PDL))

    def reject_csv_read(_path: str):
        raise AssertionError("topology-only export attempted to read a CSV")

    monkeypatch.setattr(export_bundle.pd, "read_csv", reject_csv_read)
    output = tmp_path / "topology.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export_bundle",
            "--topology-only",
            "--pdl",
            str(PDL),
            "--output",
            str(output),
        ],
    )
    export_bundle.main()
    topology = json.loads(output.read_text(encoding="utf-8"))

    assert topology["nodes"] == full["nodes"]
    assert topology["edges"] == full["edges"]
    assert topology["ticks"] == []
    assert topology["env"] == []
    assert topology["meta"]["ticks"] == 0
    assert topology["meta"]["pdl"] == PDL.name
    assert topology["meta"]["scenario"] == "topology_only"
    assert topology["meta"]["honestyNote"] == export_bundle.HONESTY_NOTE


def test_pdl_derived_runless_bundle_has_complete_frontend_placement(
    tmp_path,
) -> None:
    import json
    import subprocess

    from provider_simenv.export_bundle import build_graph

    root = Path(__file__).parents[1]
    gazetteer_module = tmp_path / "gazetteer.cjs"
    dynamics_module = tmp_path / "dynamics.cjs"
    esbuild = root / "web" / "node_modules" / ".bin" / "esbuild.cmd"

    for source, output in (
        (root / "web" / "src" / "data" / "gazetteer.ts", gazetteer_module),
        (root / "web" / "src" / "playback" / "dynamics.ts", dynamics_module),
    ):
        subprocess.run(
            [
                str(esbuild),
                str(source),
                "--bundle",
                "--platform=node",
                "--format=cjs",
                f"--outfile={output}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    nodes, edges = build_graph(str(PDL))
    bundle = {
        "meta": {
            "pdl": PDL.name,
            "scenario": "topology_only",
            "ticks": 0,
            "generatedAt": "1970-01-01T00:00:00Z",
            "honestyNote": "Approximate geographic positions — not GIS accurate",
        },
        "nodes": nodes,
        "edges": edges,
        "ticks": [],
        "env": [],
    }
    browser_contract = r"""
const fs = require('fs');
const gazetteer = require(process.argv[1]);
const { buildDynamics } = require(process.argv[2]);
const bundle = JSON.parse(fs.readFileSync(0, 'utf8'));
const scene = gazetteer.resolveScene(bundle.nodes, bundle.edges);
const dynamics = buildDynamics(bundle);
const unknown = gazetteer.resolveScene([{
  id: 'unknown',
  label: 'Unknown',
  role: 'unknown',
  entityIds: ['missing_entity'],
  hasRecordedData: false,
}], []);
const laneMarkers = scene.markers.filter((marker) => marker.nodeId.startsWith('sea_lane_'));
process.stdout.write(JSON.stringify({
  unplaced: scene.unplaced,
  markerNodeIds: scene.markers.map((marker) => marker.nodeId),
  laneMarkers,
  laneCrossings: gazetteer.PROVISIONAL_LANE_CROSSINGS,
  periods: dynamics.periods,
  emptyFrame: dynamics.frameAt(0),
  missingEnv: dynamics.envAt(0),
  unknown,
}));
"""
    completed = subprocess.run(
        [
            "node",
            "-e",
            browser_contract,
            str(gazetteer_module),
            str(dynamics_module),
        ],
        input=json.dumps(bundle),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    result = json.loads(completed.stdout)

    assert result["unplaced"] == []
    assert {node["id"] for node in nodes} <= set(result["markerNodeIds"])
    assert result["laneCrossings"] == {
        archetype.name: list(crossing)
        for crossing, archetype in TRANSITIONAL_SEA.items()
    }
    lane_positions = {
        (round(marker["lat"], 6), round(marker["lng"], 6))
        for marker in result["laneMarkers"]
    }
    assert len(result["laneMarkers"]) == len(TRANSITIONAL_SEA) == 4
    assert len(lane_positions) == 4
    assert result["periods"] == []
    assert result["emptyFrame"] == {
        "markerIntensity": {},
        "edgeIntensity": {},
    }
    assert result["missingEnv"] is None
    assert result["unknown"]["markers"] == []
    assert result["unknown"]["unplaced"] == [
        {
            "kind": "node",
            "id": "unknown (missing_entity)",
            "reason": "entity not in gazetteer",
        }
    ]


def test_second_pdl_changes_the_map_without_frontend_changes(tmp_path) -> None:
    import json
    import os
    import subprocess
    import sys

    root = Path(__file__).parents[1]
    mutated_pdl = root / "tests" / "fixtures" / "s1-soja-argentina-in-netherlands.pdl.yaml"
    base_output = tmp_path / "base-topology.json"
    mutated_output = tmp_path / "mutated-topology.json"
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    for pdl, output in ((PDL, base_output), (mutated_pdl, mutated_output)):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "provider_simenv.export_bundle",
                "--topology-only",
                "--pdl",
                str(pdl),
                "--output",
                str(output),
            ],
            cwd=root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    base = json.loads(base_output.read_text(encoding="utf-8"))
    mutated = json.loads(mutated_output.read_text(encoding="utf-8"))
    base_node_ids = [node["id"] for node in base["nodes"]]
    mutated_node_ids = [node["id"] for node in mutated["nodes"]]
    base_edge_ids = [edge["id"] for edge in base["edges"]]
    mutated_edge_ids = [edge["id"] for edge in mutated["edges"]]

    assert mutated_node_ids == [
        node_id for node_id in base_node_ids if node_id != "sea_lane_arg"
    ]
    assert set(base_edge_ids) - set(mutated_edge_ids) == {
        "wholesalers->sea_lane_arg",
        "sea_lane_arg->transport_eu_rtm",
    }
    assert set(mutated_edge_ids) - set(base_edge_ids) == {
        "wholesalers->transport_eu_rtm",
    }
    assert next(
        edge
        for edge in mutated["edges"]
        if edge["id"] == "wholesalers->transport_eu_rtm"
    ) == {
        "id": "wholesalers->transport_eu_rtm",
        "source": "wholesalers",
        "target": "transport_eu_rtm",
        "kind": "commercial",
        "isSeaCrossing": False,
    }
    assert base["ticks"] == mutated["ticks"] == []
    assert base["env"] == mutated["env"] == []

    static_source_module = tmp_path / "static-json-source.cjs"
    gazetteer_module = tmp_path / "gazetteer.cjs"
    esbuild = root / "web" / "node_modules" / ".bin" / "esbuild.cmd"
    for source, output in (
        (root / "web" / "src" / "data" / "staticJsonSource.ts", static_source_module),
        (root / "web" / "src" / "data" / "gazetteer.ts", gazetteer_module),
    ):
        subprocess.run(
            [
                str(esbuild),
                str(source),
                "--bundle",
                "--platform=node",
                "--format=cjs",
                f"--outfile={output}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    frontend_contract = r"""
const fs = require('fs');
const { parseBundle } = require(process.argv[1]);
const gazetteer = require(process.argv[2]);
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
function inspect(raw) {
  const bundle = parseBundle(raw);
  const scene = gazetteer.resolveScene(bundle.nodes, bundle.edges);
  return {
    nodeIds: bundle.nodes.map((node) => node.id),
    edgeIds: bundle.edges.map((edge) => edge.id),
    markerNodeIds: scene.markers.map((marker) => marker.nodeId),
    resolvedEdgeIds: scene.edges.map((edge) => edge.id),
    unplaced: scene.unplaced,
  };
}
process.stdout.write(JSON.stringify({
  base: inspect(input.base),
  mutated: inspect(input.mutated),
  laneFractions: gazetteer.PROVISIONAL_LANE_FRACTIONS,
}));
"""
    completed = subprocess.run(
        [
            "node",
            "-e",
            frontend_contract,
            str(static_source_module),
            str(gazetteer_module),
        ],
        input=json.dumps({"base": base, "mutated": mutated}),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    frontend = json.loads(completed.stdout)

    assert frontend["base"]["unplaced"] == []
    assert frontend["mutated"]["unplaced"] == []
    assert frontend["base"]["nodeIds"] == base_node_ids
    assert frontend["mutated"]["nodeIds"] == mutated_node_ids
    assert frontend["base"]["edgeIds"] == base_edge_ids
    assert frontend["mutated"]["edgeIds"] == mutated_edge_ids
    assert frontend["base"]["markerNodeIds"] != frontend["mutated"]["markerNodeIds"]
    assert frontend["base"]["resolvedEdgeIds"] != frontend["mutated"]["resolvedEdgeIds"]
    assert frontend["laneFractions"] == {
        "sea_lane_santos": 0.4,
        "sea_lane_paranagua": 0.6,
        "sea_lane_arg": 0.5,
        "sea_lane_usa": 0.5,
    }
