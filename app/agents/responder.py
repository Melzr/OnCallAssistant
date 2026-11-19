from app.schemas import Evidence, FinalAnswer, Hypothesis, Plan


def pick_mitigation(category: str, docs: list[dict]) -> dict | None:
    """Mitigation text is quoted verbatim from a current runbook, never generated."""
    for d in docs:
        md = d["metadata"]
        if (md["doc_type"] == "runbook" and md["status"] == "current" and md["category"] == category
                and d["id"].split("#")[-1].startswith("mitigation")):
            return d
    return None


def run(incident_id: str, plan: Plan, h: Hypothesis, approved: bool, rounds: int,
        evidence: list[Evidence], docs: list[dict]) -> FinalAnswer:
    status = "approved" if approved and h.category != "unknown" else "inconclusive"
    mit = pick_mitigation(h.category, docs) if status == "approved" else None
    return FinalAnswer(
        incident_id=incident_id, status=status, service=plan.service,
        root_cause=h.root_cause if status == "approved" else f"Inconclusive. Best hypothesis: {h.root_cause}",
        category=h.category, confidence=h.confidence if status == "approved" else min(h.confidence, 0.4),
        mitigation_ref=mit["id"] if mit else None, mitigation_text=mit["text"] if mit else None,
        citations=h.citations if status == "approved" else [], evidence=evidence, verifier_rounds=rounds,
    )
