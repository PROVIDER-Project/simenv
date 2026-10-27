from fastapi.testclient import TestClient
from playback_helpers import seed_run

from provider_simenv.playback.app import create_app
from provider_simenv.playback.store import PlaybackStore


def test_independent_api_and_lossless_json(playback_db):
    seed_run(playback_db)
    seed_run(playback_db, "failed", "failed")
    with TestClient(create_app(store_factory=lambda: PlaybackStore(playback_db),
                               allowed_origins=["http://frontend"])) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/simulations").status_code == 404
        assert client.get("/runs").json()["total"] == 2
        scene = client.get("/runs/run-1/scenarios/0/scene").json()
        assert scene["max_period"] == 2 and "frames" not in scene
        page = client.get("/runs/run-1/scenarios/0/frames?limit=1").json()
        farm = next(a for a in page["frames"][0]["agents"] if a["entity_id"] == "farm")
        assert farm["values"]["unit_price"] == 1.123456789012345
        assert client.get("/runs/missing/scenarios/0/scene").status_code == 404
        assert client.get("/runs/failed/scenarios/0/frames").status_code == 409
        for query in ["start=-1", "limit=501", "limit=0"]:
            assert client.get("/runs/run-1/scenarios/0/frames?" + query).status_code == 422
        assert client.get("/runs?limit=101").status_code == 422
        cors = client.options("/runs", headers={"Origin": "http://frontend", "Access-Control-Request-Method": "GET"})
        assert cors.headers["access-control-allow-origin"] == "http://frontend"
        cors = client.options("/runs", headers={"Origin": "http://other", "Access-Control-Request-Method": "GET"})
        assert "access-control-allow-origin" not in cors.headers


def test_empty_database_is_healthy(playback_db):
    with TestClient(create_app(store_factory=lambda: PlaybackStore(playback_db))) as client:
        assert client.get("/runs").json() == {"items": [], "total": 0}
        assert client.get("/health").status_code == 200


def test_database_outage_and_integrity_errors_are_safe(playback_db):
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    seed_run(playback_db)
    with playback_db.begin() as conn:
        conn.execute(text("DELETE FROM sim_tick WHERE period=0"))
    with TestClient(create_app(store_factory=lambda: PlaybackStore(playback_db))) as client:
        response = client.get("/runs/run-1/scenarios/0/frames")
        assert response.status_code == 500
        assert response.json() == {"detail": "Recorded data is incomplete or invalid"}

    class Offline:
        def check_health(self):
            raise OperationalError("secret SQL", {}, Exception("password=hunter2"))

    with TestClient(create_app(store_factory=Offline)) as client:
        response = client.get("/health")
        assert response.status_code == 503
        assert "hunter2" not in response.text and "secret" not in response.text
