import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['APP_API_KEY'] = 'test-key-with-minimum-length-thirty-two-chars'

from fastapi.testclient import TestClient
from api import app


def test_protected_api():
    with TestClient(app) as client:
        assert client.get('/health').json()['ok']
        assert client.get('/status').status_code == 401
        headers = {'X-API-Key': os.environ['APP_API_KEY']}
        assert client.get('/status', headers=headers).status_code == 200
        # Rejected until login and selectors are properly configured; no fake booking.
        resp = client.post('/start', headers=headers, json={
            'facility': 'Spor Merkezi', 'date': '2027-01-01', 'time': '18:00'})
        assert resp.status_code == 409
