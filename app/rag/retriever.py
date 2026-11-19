import re
from datetime import date
from pathlib import Path

from rank_bm25 import BM25Okapi

from app import config
from app.rag.metadata import Chunk, parse_document
from app.security.filters import injection_score

_TOKEN = re.compile(r"[a-z0-9_]+")

TYPE_PRIOR = {
    "diagnosis": {"postmortem": 1.0, "runbook": 0.7, "service": 0.5},
    "mitigation": {"runbook": 1.0, "postmortem": 0.5, "service": 0.4},
}


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class Retriever:
    def __init__(self, docs_dir: Path = config.DOCS_DIR):
        self.chunks: list[Chunk] = []
        self.quarantined: list[str] = []
        for p in sorted(docs_dir.rglob("*.md")):
            for c in parse_document(p):
                if injection_score(c.text) >= 0.5:
                    self.quarantined.append(c.id)
                    continue
                self.chunks.append(c)
        self.by_id = {c.id: c for c in self.chunks}
        self.bm25 = BM25Okapi([tokenize(c.embed_text) for c in self.chunks]) if self.chunks else None

    def _candidates(self, groups: list[str], service: str | None, k: int) -> list[int]:
        def allowed(c: Chunk, services: set[str] | None) -> bool:
            md = c.metadata
            if not set(md["acl"]) & set(groups) or md["status"] != "current":
                return False
            return services is None or md["service"] in services

        strict = {service} if service else None
        idx = [i for i, c in enumerate(self.chunks) if allowed(c, strict)]
        if len(idx) >= k or not service:
            return idx
        wide = {service, *config.SERVICE_GRAPH.get(service, [])}
        return [i for i, c in enumerate(self.chunks) if allowed(c, wide)]

    def search(self, query: str, *, groups: list[str], service: str | None = None,
               intent: str = "diagnosis", category: str | None = None, k: int = 5) -> list[dict]:
        cand = self._candidates(groups, service, k) if self.bm25 else []
        if not cand:
            return []
        scores = self.bm25.get_scores(tokenize(query))
        top = max(scores[i] for i in cand) or 1.0
        today = date.today()
        ranked = []
        for i in cand:
            c = self.chunks[i]
            md = c.metadata
            age_days = max((today - date.fromisoformat(md["updated_at"])).days, 0)
            recency = 1 / (1 + age_days / 365)
            score = (0.7 * scores[i] / top
                     + 0.1 * recency
                     + 0.1 * (1.0 if md["service"] == service else 0.0)
                     + 0.1 * TYPE_PRIOR[intent].get(md["doc_type"], 0.3)
                     + (0.3 if category and md["category"] == category else 0.0))
            ranked.append((score, c))
        ranked.sort(key=lambda t: t[0], reverse=True)
        hits = [(s, c) for s, c in ranked[:k]]
        hits = self._expand_related(hits, groups)
        return [self._as_result(s, c) for s, c in hits]

    def _expand_related(self, hits, groups, extra: int = 2):
        seen = {c.id for _, c in hits}
        added = 0
        out = list(hits)
        for _, c in hits:
            for rel in c.metadata["related_to"]:
                for cand in self.chunks:
                    if added >= extra:
                        return out
                    md = cand.metadata
                    if (md["document_id"] == rel and cand.id not in seen
                            and md["status"] == "current" and set(md["acl"]) & set(groups)):
                        out.append((0.0, cand))
                        seen.add(cand.id)
                        added += 1
        return out

    @staticmethod
    def _as_result(score: float, c: Chunk) -> dict:
        md = c.metadata
        header = f"[{c.id} | v{md['version']} | {md['updated_at']} | {md['doc_type']}]"
        return {"id": c.id, "score": round(score, 3), "header": header, "text": c.text, "metadata": md}
