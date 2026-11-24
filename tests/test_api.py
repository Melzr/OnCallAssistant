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


def test_trace_only_for_admin_with_debug(orch):
    c = client(orch)
    body = {"question": "orders-service failing after deploy", "service": "orders-service"}

    def ask(key, **params):
        return c.post("/ask", headers={"x-api-key": key}, params=params, json=body).json()

    assert "trace" not in ask("key-alice-sre")
    assert "trace" not in ask("key-bob-orders", debug="true")
    r = ask("key-alice-sre", debug="true")
    assert r["trace"]
    events = c.get(f"/audit/{r['incident_id']}", headers={"x-api-key": "key-alice-sre"}).json()["events"]
    assert any(e["event"] == "trace_returned" for e in events)
