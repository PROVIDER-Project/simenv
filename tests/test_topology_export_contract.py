"""Contract between the shipped PDL, bundle exporter and map data layer."""

import json
import os
import subprocess
from pathlib import Path

from provider_simenv import export_bundle
from provider_simenv.data_collector import _PROPS_BY_ROLE


ROOT = Path(__file__).resolve().parents[1]
PDL = (
    ROOT
    / "src"
    / "provider_simenv"
    / "scenarios"
    / "s1-soja.pdl.yaml"
)

EXPECTED_NODE_IDS = {
    "brazil_farms",
    "argentina_farms",
    "us_farms",
    "santos_port",
    "paranagua_port",
    "rotterdam_port",
    "hamburg_port",
    "processors",
    "feed_manufacturers",
    "eu_farmers",
    "brazil_wholesaler",
    "argentina_wholesaler",
    "us_wholesaler",
    "feed_traders",
}

EXPECTED_EDGES = {
    ("brazil_farms", "brazil_wholesaler", False),
    ("brazil_wholesaler", "santos_port", False),
    ("brazil_wholesaler", "paranagua_port", False),
    ("santos_port", "rotterdam_port", True),
    ("paranagua_port", "hamburg_port", True),
    ("argentina_farms", "argentina_wholesaler", False),
    ("argentina_wholesaler", "rotterdam_port", True),
    ("us_farms", "us_wholesaler", False),
    ("us_wholesaler", "rotterdam_port", True),
    ("rotterdam_port", "processors", False),
    ("hamburg_port", "processors", False),
    ("processors", "feed_manufacturers", False),
    ("feed_manufacturers", "feed_traders", False),
    ("feed_traders", "eu_farmers", False),
}

EXPECTED_PLACEMENTS = {
    "brazil_wholesaler": {
        "entityId": "brazil_wholesaler",
        "label": "Brazil grain originator",
        "lat": -23.0,
        "lng": -47.0,
        "illustrative": True,
    },
    "argentina_wholesaler": {
        "entityId": "argentina_wholesaler",
        "label": "Argentina grain originator",
        "lat": -32.9,
        "lng": -60.7,
        "illustrative": True,
    },
    "us_wholesaler": {
        "entityId": "us_wholesaler",
        "label": "US grain originator",
        "lat": 29.95,
        "lng": -90.07,
        "illustrative": True,
    },
    "feed_traders": {
        "entityId": "eu_feed_trader",
        "label": "EU feed distributor",
        "lat": 47.5,
        "lng": 16.0,
        "illustrative": True,
    },
}


def _build_controlled_bundle(monkeypatch):
    agent_values = {
        prop: True if prop == "active" else 1.0
        for props in _PROPS_BY_ROLE.values()
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
                **{
                    csv_column: 1.0
                    for csv_column, _ in export_bundle.ENV_COLS
                },
            }
        ]
    )

    def read_csv(path):
        if str(path).endswith("Result_Simulator_Environment.csv"):
            return env_frame
        return agent_frame

    monkeypatch.setattr(export_bundle.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(export_bundle.pd, "read_csv", read_csv)
    return export_bundle.build_bundle("unused", 1, str(PDL))


def _inspect_in_frontend(bundle, tmp_path):
    bin_name = "esbuild.cmd" if os.name == "nt" else "esbuild"
    esbuild = ROOT / "web" / "node_modules" / ".bin" / bin_name
    static_source = tmp_path / "staticJsonSource.cjs"
    gazetteer = tmp_path / "gazetteer.cjs"

    for source, output in (
        (ROOT / "web" / "src" / "data" / "staticJsonSource.ts", static_source),
        (ROOT / "web" / "src" / "data" / "gazetteer.ts", gazetteer),
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

    script = r"""
const fs = require('fs');
const { parseBundle } = require(process.argv[1]);
const { resolveScene } = require(process.argv[2]);
const bundle = parseBundle(JSON.parse(fs.readFileSync(0, 'utf8')));
const scene = resolveScene(bundle.nodes, bundle.edges);
const declaredIds = new Set([
  'brazil_wholesaler',
  'argentina_wholesaler',
  'us_wholesaler',
  'feed_traders',
]);
const declared = Object.fromEntries(
  scene.markers
    .filter((marker) => declaredIds.has(marker.nodeId))
    .map((marker) => [marker.nodeId, {
      label: marker.label,
      lat: marker.lat,
      lng: marker.lng,
      illustrative: marker.illustrative,
    }]),
);
process.stdout.write(JSON.stringify({
  markerCount: scene.markers.length,
  edgeCount: scene.edges.length,
  unplaced: scene.unplaced,
  declared,
}));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(static_source), str(gazetteer)],
        input=json.dumps(bundle),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def test_shipped_pdl_bundle_matches_map_contract(tmp_path, monkeypatch):
    bundle = _build_controlled_bundle(monkeypatch)
    nodes = {node["id"]: node for node in bundle["nodes"]}
    edges = {
        (edge["source"], edge["target"], edge["isSeaCrossing"])
        for edge in bundle["edges"]
    }

    assert set(nodes) == EXPECTED_NODE_IDS
    assert "wholesalers" not in nodes
    assert not any(node_id.startswith("sea_transport_") for node_id in nodes)
    assert edges == EXPECTED_EDGES
    assert len({edge["id"] for edge in bundle["edges"]}) == 14
    assert all(
        edge["source"] in nodes and edge["target"] in nodes
        for edge in bundle["edges"]
    )

    placements = {
        node_id: node["placements"][0]
        for node_id, node in nodes.items()
        if node["placements"]
    }
    assert placements == EXPECTED_PLACEMENTS
    assert {node_id for node_id, node in nodes.items() if node["hasRecordedData"]} == {
        tick["nodeId"] for tick in bundle["ticks"]
    }
    assert len(bundle["ticks"]) == 10
    assert len(bundle["env"]) == bundle["meta"]["ticks"] == 1

    frontend = _inspect_in_frontend(bundle, tmp_path)
    assert frontend == {
        "markerCount": 16,
        "edgeCount": 14,
        "unplaced": [],
        "declared": {
            node_id: {
                key: value
                for key, value in placement.items()
                if key != "entityId"
            }
            for node_id, placement in EXPECTED_PLACEMENTS.items()
        },
    }
