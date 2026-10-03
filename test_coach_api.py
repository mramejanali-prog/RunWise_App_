import os
os.environ['DATABASE_URL'] = 'sqlite:///./test_runwise_v015.db'
os.environ['JWT_SECRET'] = 'test-secret-runwise-release-32-chars-min'

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    r = client.get('/health')
    assert r.status_code == 200
    assert r.json()['status'] == 'ok'
    assert r.json()['version'] == '1.0.0'

def test_plan_progression():
    r = client.post('/v1/coach/plan', json={
        'weekly_km': 30, 'previous_weekly_km': 28, 'load_score': 45,
        'baseline_pace_seconds_per_km': 330
    })
    assert r.status_code == 200
    body = r.json()
    assert 30 < body['weekly_target_km'] <= 38
    assert len(body['sessions']) == 7

def test_plan_taper():
    r = client.post('/v1/coach/plan', json={
        'weekly_km': 40, 'load_score': 50, 'next_race_days': 5
    })
    assert r.status_code == 200
    assert 'taper' in r.json()['reason']
    assert r.json()['weekly_target_km'] < 40
