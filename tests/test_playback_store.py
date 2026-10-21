import pytest
from playback_helpers import seed_run
from sqlalchemy import text

from provider_simenv.playback.store import (
    PlaybackIntegrityError,
    PlaybackNotFound,
    PlaybackStore,
    PlaybackUnavailable,
)


def test_ranges_preserve_every_agent_and_value(playback_db):
    seed_run(playback_db)
    seed_run(playback_db, "other")
    store = PlaybackStore(playback_db)
    page = store.get_frames("run-1", 0, 1, 1)
    assert page.next_start == 2
    assert len(page.frames) == 1
    frame = page.frames[0]
    assert frame.period == 1
    farms = [a for a in frame.agents if a.entity_id == "farm"]
    assert [(a.agent_id, a.values["unit_price"]) for a in farms] == [
        (0, 2.1234567890123452), (1, 3.1234567890123452)]
    assert store.get_frames("run-1", 1, 2, 100).next_start is None
    assert store.get_frames("run-1", 0, 3, 100).frames == []
    assert store.get_frames("run-1", 1, 0, 1).frames[0].agents[1].values["unit_price"] == 2.1234567890123452


def test_catalogue_scene_and_unavailable_runs(playback_db):
    seed_run(playback_db)
    seed_run(playback_db, "failed", "failed")
    seed_run(playback_db, "legacy", scene=False)
    store = PlaybackStore(playback_db)
    runs = store.list_runs(100, 0)
    assert runs.total == 3
    assert {r.id: r.playable for r in runs.items} == {"run-1": True, "failed": False, "legacy": False}
    scene = store.get_scene("run-1", 1)
    assert scene.max_period == 2
    assert "frames" not in scene.model_dump()
    with pytest.raises(PlaybackNotFound):
        store.get_scene("run-1", 8)
    with pytest.raises(PlaybackUnavailable):
        store.get_frames("failed", 0, 0, 1)
    with playback_db.begin() as conn:
        conn.execute(text("UPDATE sim_run SET scene=CAST(:scene AS jsonb) WHERE run_id='run-1'"),
                     {"scene": '{"schema_version":99}'})
    assert not next(r for r in store.list_runs(100, 0).items if r.id == "run-1").playable


def test_missing_environment_and_nonfinite_are_integrity_errors(playback_db):
    seed_run(playback_db)
    store = PlaybackStore(playback_db)
    with playback_db.begin() as conn:
        conn.execute(text("UPDATE sim_tick SET value='NaN' WHERE period=0"))
    with pytest.raises(PlaybackIntegrityError):
        store.get_frames("run-1", 0, 0, 1)
    with playback_db.begin() as conn:
        conn.execute(text("DELETE FROM sim_tick WHERE period=1"))
    with pytest.raises(PlaybackIntegrityError):
        store.get_frames("run-1", 0, 1, 1)


def test_legacy_provenance_is_checked_without_reading_ticks(playback_db, tmp_path):
    from pathlib import Path

    from provider_simenv.export_bundle import _sha256
    from provider_simenv.topology import sidecar_path

    seed_run(playback_db, scene=False)
    pdl = Path(__file__).parents[1] / "src/provider_simenv/scenarios/s1-soja.pdl.yaml"
    with playback_db.begin() as conn:
        conn.execute(text("UPDATE sim_run SET pdl_sha256=:pdl, roster_sha256=:roster WHERE run_id='run-1'"),
                     {"pdl": _sha256(pdl), "roster": _sha256(sidecar_path(pdl))})
    store = PlaybackStore(playback_db)
    assert store.list_runs(10, 0).items[0].playable
    assert store.get_scene("run-1", 0).nodes
    with playback_db.begin() as conn:
        conn.execute(text("UPDATE sim_run SET roster_sha256='changed' WHERE run_id='run-1'"))
    assert not store.list_runs(10, 0).items[0].playable
    with pytest.raises(PlaybackUnavailable):
        store.get_scene("run-1", 0)
