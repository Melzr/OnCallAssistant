"""Run every scenario against the real LLM and report latency, model usage and cost.

  python scripts/benchmark.py [--runs N] [--json out.json]

Costs are list-price estimates (USD per 1M tokens); the gateway may bill differently.
"""
import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, llm  # noqa: E402
from app.orchestrator import Orchestrator  # noqa: E402
from app.schemas import AskRequest  # noqa: E402
from scripts.simulate import EXPECTED, QUESTIONS  # noqa: E402
from simulator import scenarios  # noqa: E402

PRICES = {"haiku": (0.10, 0.50), "sonnet": (2.00, 10.00), "opus": (4.00, 20.00)}


def family(model: str) -> str:
    m = model.lower()
    return next((f for f in PRICES if f in m), "unknown")


def cost(model: str, tin: int, tout: int) -> float:
    pin, pout = PRICES.get(family(model), (0, 0))
    return (tin * pin + tout * pout) / 1e6


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))] if xs else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--json")
    args = ap.parse_args()
    if not llm.online():
        print("No ANTHROPIC_API_KEY: refusing to benchmark in offline mode")
        return 2

    user = config.USERS["key-alice-sre"]
    rows, calls, errors = [], defaultdict(list), 0
    for sid in scenarios.scenario_ids():
        for i in range(args.runs):
            orch = Orchestrator()
            env = scenarios.build(sid)
            t0 = time.time()
            a = orch.handle(user, AskRequest(question=QUESTIONS[sid], service=env.service, scenario=sid))
            wall = int((time.time() - t0) * 1000)
            llm_calls = [t for t in a.trace if t["event"] == "llm_call"]
            errs = [t for t in a.trace if t["event"] == "llm_error"]
            errors += len(errs)
            for t in llm_calls:
                calls[t["model"]].append(t)
            rows.append({"scenario": sid, "run": i, "status": a.status, "expected": EXPECTED[sid],
                         "category": a.category, "confidence": a.confidence, "rounds": a.verifier_rounds,
                         "ms": wall, "llm_calls": len(llm_calls), "llm_errors": len(errs),
                         "escalated": any(family(t["model"]) == "opus" for t in llm_calls),
                         "cost": sum(cost(t["model"], t.get("input_tokens", 0), t.get("output_tokens", 0))
                                     for t in llm_calls)})
            r = rows[-1]
            print(f"{sid:20} run{i} {r['status']:12} rounds={r['rounds']} calls={r['llm_calls']} "
                  f"errs={r['llm_errors']} {wall}ms ${r['cost']:.4f}", flush=True)

    print("\nPer scenario")
    for sid in scenarios.scenario_ids():
        rs = [r for r in rows if r["scenario"] == sid]
        ok = sum(r["status"] == r["expected"] for r in rs)
        ms = [r["ms"] for r in rs]
        print(f"{sid:20} correct={ok}/{len(rs)} p50={pct(ms, .5)}ms p95={pct(ms, .95)}ms "
              f"avg_cost=${statistics.mean(r['cost'] for r in rs):.4f} "
              f"escalated={sum(r['escalated'] for r in rs)}/{len(rs)}")

    print("\nPer model")
    tot = 0.0
    per_model = {}
    for model, ts in calls.items():
        tin = sum(t.get("input_tokens", 0) for t in ts)
        tout = sum(t.get("output_tokens", 0) for t in ts)
        ms = [t["ms"] for t in ts]
        c = cost(model, tin, tout)
        tot += c
        per_model[model] = {"calls": len(ts), "input": tin, "output": tout, "p50_ms": pct(ms, .5),
                            "p95_ms": pct(ms, .95), "cost": c}
        print(f"{model:24} calls={len(ts)} in={tin} out={tout} p50={pct(ms, .5)}ms "
              f"p95={pct(ms, .95)}ms cost=${c:.4f}")
    allms = [r["ms"] for r in rows]
    print(f"\nTotal cost ${tot:.4f} over {len(rows)} incidents (${tot / len(rows):.4f} each); "
          f"end-to-end p50={pct(allms, .5)}ms p95={pct(allms, .95)}ms; "
          f"correct {sum(r['status'] == r['expected'] for r in rows)}/{len(rows)}; llm_errors={errors}")
    if args.json:
        Path(args.json).write_text(json.dumps({"rows": rows, "models": per_model}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
