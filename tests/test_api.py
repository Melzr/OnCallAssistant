import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app import config
from app.api import main


def client(orch):
    main._orch = orch
    main._hits.clear()
    return TestClient(main.app)


def test_auth_required(orch):
    assert client(orch).post("/ask", json={"question": "payments-service down"}).status_code == 401


def test_ask_ok_and_rbac(orch):
    c = client(orch)
    r = c.post("/ask", headers={"x-api-key": "key-alice-sre"},
               json={"question": "payments-service errors", "service": "payments-service"})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    r = c.post("/ask", headers={"x-api-key": "key-bob-orders"},
               json={"question": "payments-service errors", "service": "payments-service"})
    assert r.status_code == 403


def test_alert_signature(orch):
    c = client(orch)
    body = json.dumps({"question": "auth-service errors", "service": "auth-service"}).encode()
    assert c.post("/alerts", content=body, headers={"x-signature": "bad"}).status_code == 401
    sig = hmac.new(config.alert_secret().encode(), body, hashlib.sha256).hexdigest()
    assert c.post("/alerts", content=body, headers={"x-signature": sig}).status_code == 200
