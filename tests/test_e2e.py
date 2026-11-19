import pytest

from app.schemas import AskRequest


@pytest.mark.parametrize("scenario,service,category,runbook", [
    ("db_pool_exhaustion", "payments-service", "db_pool_exhaustion", "rb-payments-db-pool"),
    ("bad_deploy", "orders-service", "bad_deploy", "rb-bad-deploy-rollback"),
    ("tls_expiry", "auth-service", "tls_expiry", "rb-tls-cert-expiry"),
])
def test_root_cause_and_mitigation(orch, alice, scenario, service, category, runbook):
    a = orch.handle(alice, AskRequest(question=f"{service} is failing, how do I fix it?", service=service,
                                      scenario=scenario))
    assert a.status == "approved"
    assert a.category == category
    assert a.mitigation_ref.startswith(runbook)
    assert a.citations and all(c in {d for d in a.citations} for c in a.citations)


def test_obsolete_runbook_never_cited(orch, alice):
    a = orch.handle(alice, AskRequest(question="payments-service pool exhausted, mitigation?",
                                      service="payments-service"))
    assert not any("@1.4" in c for c in a.citations)
    assert "Restart the postgres instance" not in (a.mitigation_text or "")


def test_cache_hit_second_time(orch, alice):
    req = AskRequest(question="payments-service latency high", service="payments-service")
    assert not orch.handle(alice, req).cached
    assert orch.handle(alice, req).cached


def test_audit_chain_and_slack_outbox(orch, alice, tmp_path):
    a = orch.handle(alice, AskRequest(question="payments-service errors", service="payments-service"))
    assert orch.audit.verify()
    assert {e["event"] for e in orch.audit.read(a.incident_id)} >= {"plan", "hypothesis", "critique", "final"}
    assert (tmp_path / "slack_outbox.log").exists()
