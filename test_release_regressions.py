import os
from pathlib import Path

DB = Path(__file__).with_name("test_release.db")
if DB.exists(): DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["JWT_SECRET"] = "test-secret-runwise-release-32-chars-min"
os.environ["APP_ENV"] = "test"

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def auth():
    payload = {"email": "release@example.com", "password": "password123"}
    r = client.post("/v1/auth/register", json=payload)
    if r.status_code == 409:
        r = client.post("/v1/auth/login", json=payload)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_ready():
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_auth_and_me():
    headers = auth()
    r = client.get("/v1/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "release@example.com"


def test_race_round_trip():
    headers = auth()
    race = {
        "id": "race-1", "provider": "TCHACO", "external_id": "ext-1",
        "name": "Corrida Teste", "date": "2026-11-01T08:00:00Z",
        "distance_meters": 10000, "location": "Luanda", "registration_status": "REGISTERED"
    }
    r = client.post("/v1/sync/races", headers=headers, json=[race])
    assert r.status_code == 200
    r = client.get("/v1/sync/races", headers=headers)
    assert r.status_code == 200
    assert r.json()["items"][0]["id"] == "race-1"


def test_activity_stale_write_is_rejected():
    headers = auth()
    activity = {
        "id": "activity-1", "source": "TEST", "kind": "TRAINING",
        "started_at": "2026-10-01T07:00:00Z", "duration_seconds": 1800,
        "distance_meters": 5000
    }
    assert client.post("/v1/sync/activities", headers=headers, json=[activity]).status_code == 200
    pulled = client.get("/v1/sync/activities", headers=headers).json()["items"]
    server_time = pulled[0]["updated_at"]
    stale = dict(activity, distance_meters=6000)
    r = client.post(f"/v1/sync/activities?base_since=2026-01-01T00:00:00Z", headers=headers, json=[stale])
    assert r.status_code == 200
    assert "activity-1" in r.json()["conflicts"]


def test_planned_workout_stale_write_returns_conflict():
    headers = auth()
    workout = {
        "id": "workout-1", "date": "2026-10-04T07:00:00Z", "type": "EASY",
        "title": "Corrida leve", "description": "5 km", "target_distance_meters": 5000,
        "completed": False, "skipped": False
    }
    first = client.post("/v1/sync/planned-workouts", headers=headers, json=[workout])
    assert first.status_code == 200
    stale = dict(workout, completed=True)
    second = client.post("/v1/sync/planned-workouts?base_since=2026-01-01T00:00:00Z", headers=headers, json=[stale])
    assert second.status_code == 200
    assert "workout-1" in second.json()["conflicts"]


def test_activity_current_version_allows_explicit_local_resolution():
    headers = auth()
    activity = {
        "id": "activity-force-local", "source": "TEST", "kind": "TRAINING",
        "started_at": "2026-10-02T07:00:00Z", "duration_seconds": 1800,
        "distance_meters": 5000
    }
    assert client.post("/v1/sync/activities", headers=headers, json=[activity]).status_code == 200
    current = client.get("/v1/sync/activities", headers=headers).json()["items"]
    updated_at = next(row["updated_at"] for row in current if row["id"] == activity["id"])
    local = dict(activity, distance_meters=5500)
    r = client.post(f"/v1/sync/activities?base_since={updated_at}", headers=headers, json=[local])
    assert r.status_code == 200
    assert r.json()["accepted"] == 1
    latest = client.get("/v1/sync/activities", headers=headers).json()["items"]
    assert next(row["distance_meters"] for row in latest if row["id"] == activity["id"]) == 5500
