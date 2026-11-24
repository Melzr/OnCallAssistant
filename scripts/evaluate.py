"""Evaluate model, agents and RAG. Model and agent sections need ANTHROPIC_API_KEY.

  python scripts/evaluate.py [--runs N] [--json var/evaluation.json]
"""
import argparse
import json
import statistics
import sys
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel  # noqa: E402

from app import config, llm  # noqa: E402
from app.agents import investigator, triage, verifier  # noqa: E402
from app.agents.context import render_docs  # noqa: E402
from app.orchestrator import Orchestrator  # noqa: E402
from app.rag.retriever import Retriever, tokenize  # noqa: E402
from app.schemas import AskRequest, Hypothesis  # noqa: E402
from evaluation import gold, metrics  # noqa: E402
from scripts.benchmark import cost, family  # noqa: E402
from scripts.simulate import QUESTIONS  # noqa: E402
from simulator import scenarios  # noqa: E402

mean = statistics.mean


class Judge(BaseModel):
    score: float
    reason: str


def judge(system: str, user: str) -> float:
    try:
        j, _ = llm.complete_json(model=config.MODEL_TRIAGE, system=system, user=user, schema=Judge,
                                 max_tokens=300, name="judge")
        return max(0.0, min(1.0, j.score))
    except (llm.LLMUnavailable, llm.LLMRefusal):
        return float("nan")


def eval_rag(retriever: Retriever) -> dict:
    out = defaultdict(list)
    stale = {c.id for c in retriever.chunks if c.metadata["status"] != "current"}
    stale |= {"rb-payments-db-pool@1.4#mitigation"}
    for g in gold.RETRIEVAL:
        for _ in range(20):
            t0 = time.perf_counter()
            hits = retriever.search(g["q"], groups=g["groups"], service=g["service"], intent=g["intent"])
            out["ms"].append((time.perf_counter() - t0) * 1000)
        ranked = [h["id"] for h in hits]
        rel = g["relevant"]
        for k in (1, 3, 5):
            out[f"p@{k}"].append(metrics.precision_at_k(ranked, rel, k))
            out[f"r@{k}"].append(metrics.recall_at_k(ranked, rel, k))
        out["mrr"].append(metrics.reciprocal_rank(ranked, rel))
        out["stale_leak"].append(bool(set(ranked) & stale))
    bob = config.USERS["key-bob-orders"]
    leak = retriever.search("payments connection pool exhausted", groups=bob["groups"], service="payments-service")
    out["acl_leak"] = [any(h["metadata"]["service"] == "payments-service" for h in leak)]
    res = {k: mean(v) for k, v in out.items()}
    res["ms_p95"] = metrics.percentile(out["ms"], 0.95)
    res["queries"] = len(gold.RETRIEVAL)
    res["chunks"] = len(retriever.chunks)
    return res


def eval_context(retriever: Retriever) -> dict:
    """Useful-context coverage and prompt trimming over the docs each scenario hands to the LLM."""
    cov, dens, saved = [], [], []
    user = config.USERS["key-alice-sre"]
    for sid, g in gold.SCENARIOS.items():
        env = scenarios.build(sid)
        plan, _ = triage.run(QUESTIONS[sid], env.service, user["services"])
        ev = investigator.gather(env, plan, user["services"])
        docs = investigator.sanitize_docs(investigator.retrieve(retriever, plan, ev, user["groups"]))
        shown = {d["id"] for d in sorted(docs, key=lambda d: d["score"], reverse=True)[:config.MAX_PROMPT_DOCS]}
        if g["useful_docs"]:
            cov.append(len(g["useful_docs"] & shown) / len(g["useful_docs"]))
            dens.append(len(g["useful_docs"] & shown) / max(len(shown), 1))
        full = sum(len(d["text"]) + len(d["header"]) for d in docs)
        saved.append(1 - len(render_docs(docs)) / full if full else 0.0)
    return {"useful_context_coverage": mean(cov), "useful_context_density": mean(dens),
            "prompt_chars_saved": mean(saved)}


def run_pipeline(runs: int, retriever: Retriever, session: str) -> list[dict]:
    user = config.USERS["key-alice-sre"]
    rows = []
    for sid, g in gold.SCENARIOS.items():
        for i in range(runs):
            llm.CACHE_BUST = f"{session}-{sid}-{i}"
            orch = Orchestrator(retriever)
            env = scenarios.build(sid)
            t0 = time.time()
            a = orch.handle(user, AskRequest(question=QUESTIONS[sid], service=env.service, scenario=sid))
            wall = int((time.time() - t0) * 1000)
            tr = a.trace
            ev_ids = {e["id"] for e in (a.evidence and [x.model_dump() for x in a.evidence]) or []}
            hyp = next((t for t in reversed(tr) if t["event"] == "hypothesis"), {})
            crit = next((t for t in reversed(tr) if t["event"] == "critique"), {})
            calls = [t for t in tr if t["event"] == "llm_call"]
            tools = [(t["tool"], t["input"]) for t in tr if t["event"] == "tool_call"]
            ref = scenarios.build(sid).root_cause
            cand = a.root_cause
            rows.append({
                "scenario": sid, "run": i, "ms": wall, "status": a.status, "category": a.category,
                "rounds": a.verifier_rounds, "calls": calls,
                "errors": sum(t["event"] == "llm_error" for t in tr),
                "error_details": [t.get("detail") for t in tr if t["event"] == "llm_error"],
                "nodes": [(t["node"], t["ms"]) for t in tr if t["event"] == "node"],
                "status_ok": a.status == g["status"], "category_ok": a.category == g["category"],
                "mitigation_ok": a.mitigation_ref == g["mitigation"],
                "grounded": all(c in retriever.by_id for c in hyp.get("citations", []))
                            and set(hyp.get("evidence_ids", [])) <= ev_ids,
                "verifier_ok": bool(crit.get("approved")) == (hyp.get("category") == g["category"]),
                "dup_tools": len(tools) - len(set(tools)), "tool_calls": len(tools),
                "bleu": metrics.bleu(ref, cand), "rouge1": metrics.rouge_n(ref, cand, 1),
                "rouge2": metrics.rouge_n(ref, cand, 2), "rougeL": metrics.rouge_l(ref, cand),
                "ref": ref, "cand": cand,
                "cost": sum(cost(t["model"], t.get("input_tokens", 0), t.get("output_tokens", 0)) for t in calls),
            })
            print(f"{sid:20} run{i} {a.status:12} {wall}ms", flush=True)
    return rows


def eval_semantic(rows: list[dict], sim: metrics.TfidfSimilarity) -> None:
    for r in rows:
        r["tfidf_cos"] = sim(r["ref"], r["cand"])
        r["judge"] = judge(
            "Rate from 0 to 1 how semantically equivalent the candidate root cause is to the reference. "
            "1 = same cause, 0 = unrelated or contradictory. Ignore wording and length.",
            f"reference: {r['ref']}\ncandidate: {r['cand']}")


def eval_dialogue(retriever: Retriever) -> dict:
    """Feed the verifier flawed hypotheses and check it rejects them and the investigator recovers."""
    user = config.USERS["key-alice-sre"]
    probes = []
    for sid in ("db_pool_exhaustion", "bad_deploy", "tls_expiry"):
        env = scenarios.build(sid)
        plan, _ = triage.run(QUESTIONS[sid], env.service, user["services"])
        ev = investigator.gather(env, plan, user["services"])
        docs = investigator.sanitize_docs(investigator.retrieve(retriever, plan, ev, user["groups"]))
        cites = [d["id"] for d in docs if d["metadata"].get("category") == env.category][:2]
        ids = [e.id for e in ev]
        wrong = next(c for c in ("tls_expiry", "bad_deploy", "db_pool_exhaustion") if c != env.category)
        probes.append((sid, "wrong_category", env, plan, ev, docs, Hypothesis(
            root_cause=f"The incident is caused by {wrong}", category=wrong, confidence=0.9,
            evidence_ids=ids, citations=cites)))
        probes.append((sid, "unsupported_claim", env, plan, ev, docs, Hypothesis(
            root_cause="A failing disk on the database host corrupted writes and caused the outage",
            category=env.category, confidence=0.9, evidence_ids=ids, citations=cites)))
    res = defaultdict(list)
    for sid, kind, env, plan, ev, docs, h in probes:
        crit, _ = verifier.run(h, ev, docs)
        res[f"reject_{kind}"].append(not crit.approved)
        if crit.approved:
            continue
        res["specificity"].append(judge(
            "Rate from 0 to 1 how specific and actionable this verifier critique is: does it point to concrete "
            "evidence or document ids and say what is wrong? 1 = precise, 0 = vague or generic.",
            f"hypothesis: {h.root_cause}\ncritique issues: {crit.issues}"))
        fixed, _ = investigator.run(plan, ev, docs, crit)
        ok = fixed.category == env.category and "disk" not in fixed.root_cause.lower()
        res["recovered"].append(ok)
        res["confidence_after"].append(fixed.confidence)
    return {k: mean(v) for k, v in res.items()} | {"probes": len(probes)}


def eval_redundancy(retriever: Retriever) -> dict:
    user = config.USERS["key-alice-sre"]
    orch = Orchestrator(retriever)
    env = scenarios.build("db_pool_exhaustion")
    req = AskRequest(question=QUESTIONS["db_pool_exhaustion"], service=env.service, scenario="db_pool_exhaustion")
    t0 = time.time()
    first = orch.handle(user, req)
    t1 = time.time()
    second = orch.handle(user, req)
    t2 = time.time()
    return {"cache_first_ms": int((t1 - t0) * 1000), "cache_second_ms": int((t2 - t1) * 1000),
            "cache_tokens_saved": first.tokens, "cache_second_cached": second.cached,
            "cache_second_tokens": 0 if second.cached else second.tokens}


def pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--json", default="var/evaluation.json")
    args = ap.parse_args()
    if not llm.online():
        print("No ANTHROPIC_API_KEY: refusing to evaluate in offline mode")
        return 2

    retriever = Retriever()
    sim = metrics.TfidfSimilarity([c.text for c in retriever.chunks])
    print("== RAG (offline) ==")
    rag = eval_rag(retriever)
    ctx = eval_context(retriever)
    session = uuid.uuid4().hex[:8]
    print("== Pipeline (unique request tag per incident) ==")
    rows = run_pipeline(args.runs, retriever, session)
    llm.CACHE_BUST = ""
    print("== Semantic scoring ==")
    eval_semantic(rows, sim)
    print("== Agent dialogue probes ==")
    dlg = eval_dialogue(retriever)
    red = eval_redundancy(retriever)

    calls = [c for r in rows for c in r["calls"]]
    by_model = defaultdict(list)
    for c in calls:
        by_model[c["model"]].append(c)
    node_ms = defaultdict(list)
    for r in rows:
        for n, ms in r["nodes"]:
            node_ms[n].append(ms)
    ms = [r["ms"] for r in rows]
    cat_by_scn = defaultdict(list)
    for r in rows:
        cat_by_scn[r["scenario"]].append(r["category"])
    consistency = mean(Counter(v).most_common(1)[0][1] / len(v) for v in cat_by_scn.values())
    tot_cost = sum(r["cost"] for r in rows)

    report = {
        "model": {
            "incidents": len(rows), "e2e_p50_ms": metrics.percentile(ms, .5), "e2e_p95_ms": metrics.percentile(ms, .95),
            "tokens_in": sum(c.get("input_tokens", 0) for c in calls),
            "tokens_out": sum(c.get("output_tokens", 0) for c in calls),
            "cost_total": tot_cost, "cost_per_incident": tot_cost / len(rows),
            "llm_errors": sum(r["errors"] for r in rows),
            "error_details": Counter(d for r in rows for d in r["error_details"]).most_common(5),
            "per_model": {m: {"calls": len(cs), "in": sum(c.get("input_tokens", 0) for c in cs),
                              "out": sum(c.get("output_tokens", 0) for c in cs),
                              "p50_ms": metrics.percentile([c["ms"] for c in cs], .5),
                              "p95_ms": metrics.percentile([c["ms"] for c in cs], .95)}
                          for m, cs in by_model.items()},
            "bleu": mean(r["bleu"] for r in rows), "rouge1": mean(r["rouge1"] for r in rows),
            "rouge2": mean(r["rouge2"] for r in rows), "rougeL": mean(r["rougeL"] for r in rows),
            "tfidf_cos": mean(r["tfidf_cos"] for r in rows),
            "judge": mean(r["judge"] for r in rows if r["judge"] == r["judge"]),
        },
        "agents": {
            "category_ok": mean(r["category_ok"] for r in rows), "status_ok": mean(r["status_ok"] for r in rows),
            "mitigation_ok": mean(r["mitigation_ok"] for r in rows), "grounded": mean(r["grounded"] for r in rows),
            "verifier_ok": mean(r["verifier_ok"] for r in rows), "self_consistency": consistency,
            "first_round_rate": mean(r["rounds"] == 1 for r in rows), "avg_rounds": mean(r["rounds"] for r in rows),
            "node_ms": {n: {"p50": metrics.percentile(v, .5), "p95": metrics.percentile(v, .95)}
                        for n, v in node_ms.items()},
            "dialogue": dlg,
            "redundancy": red | {"dup_tool_calls": sum(r["dup_tools"] for r in rows),
                                 "tool_calls": sum(r["tool_calls"] for r in rows),
                                 "prompt_chars_saved": ctx["prompt_chars_saved"]},
        },
        "rag": rag | ctx,
        "rows": [{k: v for k, v in r.items() if k not in ("calls",)} for r in rows],
    }
    Path(args.json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json).write_text(json.dumps(report, indent=2, default=str))
    m, a, r = report["model"], report["agents"], report["rag"]
    print("\n## MODEL")
    print(f"incidents={m['incidents']} e2e p50={m['e2e_p50_ms']:.0f}ms p95={m['e2e_p95_ms']:.0f}ms "
          f"tokens in/out={m['tokens_in']}/{m['tokens_out']} cost=${m['cost_total']:.4f} "
          f"(${m['cost_per_incident']:.4f}/incident) llm_errors={m['llm_errors']}")
    print("errors:", m["error_details"])
    for name, v in m["per_model"].items():
        print(f"  {name}: calls={v['calls']} in={v['in']} out={v['out']} p50={v['p50_ms']:.0f}ms p95={v['p95_ms']:.0f}ms")
    print(f"BLEU={m['bleu']:.2f} ROUGE-1={m['rouge1']:.2f} ROUGE-2={m['rouge2']:.2f} ROUGE-L={m['rougeL']:.2f} "
          f"TFIDF-cos={m['tfidf_cos']:.2f} LLM-judge={m['judge']:.2f}")
    print("\n## AGENTS")
    print(f"category={pct(a['category_ok'])} status={pct(a['status_ok'])} mitigation={pct(a['mitigation_ok'])} "
          f"grounded={pct(a['grounded'])} verifier_ok={pct(a['verifier_ok'])} self_consistency={pct(a['self_consistency'])} "
          f"first_round={pct(a['first_round_rate'])} avg_rounds={a['avg_rounds']:.2f}")
    print("node latency:", {n: f"p50={v['p50']:.0f}/p95={v['p95']:.0f}ms" for n, v in a["node_ms"].items()})
    print("dialogue:", {k: round(v, 2) for k, v in a["dialogue"].items()})
    print("redundancy:", a["redundancy"])
    print("\n## RAG")
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
