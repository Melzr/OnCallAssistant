import pytest

from app import config
from app.orchestrator import Orchestrator
from app.rag.retriever import Retriever
from app.security.audit import AuditLog


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(config, "VAR_DIR", tmp_path)


@pytest.fixture(scope="session")
def retriever():
    return Retriever()


@pytest.fixture
def orch(retriever, tmp_path):
    return Orchestrator(retriever, AuditLog(tmp_path / "audit.jsonl"))


@pytest.fixture
def alice():
    return config.USERS["key-alice-sre"]


@pytest.fixture
def bob():
    return config.USERS["key-bob-orders"]
