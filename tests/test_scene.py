from pathlib import Path

from provider_simenv.scene import build_scene


def test_scene_contains_topology_without_measurements():
    pdl = Path(__file__).parents[1] / "src/provider_simenv/scenarios/s1-soja.pdl.yaml"
    scene = build_scene(pdl)
    assert scene["schema_version"] == 1
    assert scene["nodes"] and scene["edges"]
    assert any(node["id"] == "brazil_farms" for node in scene["nodes"])
    assert "ticks" not in scene and "env" not in scene
