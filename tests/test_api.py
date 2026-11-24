from fastapi.testclient import TestClient

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
