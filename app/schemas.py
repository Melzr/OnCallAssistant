from typing import Literal

from pydantic import BaseModel, Field

Intent = Literal["diagnosis", "mitigation"]


class AskRequest(BaseModel):
    question: str = Field(min_length=3)
    service: str | None = None


class Plan(BaseModel):
    incident_goal: str
    service: str
    severity: Literal["low", "medium", "high"]
    intent: Intent
    tools: list[str]


class Evidence(BaseModel):
    id: str
    kind: Literal["metric", "log", "deploy", "doc"]
    summary: str
    source: str


class Hypothesis(BaseModel):
    root_cause: str
    category: str
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str]
    citations: list[str]
    missing: list[str] = []


class Critique(BaseModel):
    approved: bool
    issues: list[str]
    score: float = Field(ge=0, le=1)


class FinalAnswer(BaseModel):
    incident_id: str
    status: Literal["approved", "inconclusive", "blocked"]
    service: str
    root_cause: str
    category: str
    confidence: float
    mitigation_ref: str | None
    mitigation_text: str | None
    citations: list[str]
    evidence: list[Evidence]
    verifier_rounds: int
    cached: bool = False
    tokens: int = 0
    trace: list[dict] = []
