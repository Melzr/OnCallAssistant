import math
import re
from collections import Counter

_TOKEN = re.compile(r"[a-z0-9_]+")


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _ngrams(toks: list[str], n: int) -> Counter:
    return Counter(tuple(toks[i:i + n]) for i in range(len(toks) - n + 1))


def bleu(reference: str, candidate: str, max_n: int = 4) -> float:
    """Sentence BLEU with add-one smoothing on n-gram precisions."""
    ref, cand = tokens(reference), tokens(candidate)
    if not cand:
        return 0.0
    logs = 0.0
    for n in range(1, max_n + 1):
        c, r = _ngrams(cand, n), _ngrams(ref, n)
        match = sum(min(v, r[g]) for g, v in c.items())
        total = max(sum(c.values()), 0)
        logs += math.log((match + 1) / (total + 1))
    bp = 1.0 if len(cand) >= len(ref) else math.exp(1 - len(ref) / len(cand))
    return bp * math.exp(logs / max_n)


def _f1(match: int, n_ref: int, n_cand: int) -> float:
    if not match:
        return 0.0
    p, r = match / n_cand, match / n_ref
    return 2 * p * r / (p + r)


def rouge_n(reference: str, candidate: str, n: int = 1) -> float:
    r, c = _ngrams(tokens(reference), n), _ngrams(tokens(candidate), n)
    return _f1(sum(min(v, r[g]) for g, v in c.items()), sum(r.values()), sum(c.values()))


def rouge_l(reference: str, candidate: str) -> float:
    a, b = tokens(reference), tokens(candidate)
    if not a or not b:
        return 0.0
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            dp[i + 1][j + 1] = dp[i][j] + 1 if x == y else max(dp[i][j + 1], dp[i + 1][j])
    return _f1(dp[-1][-1], len(a), len(b))


class TfidfSimilarity:
    """Cosine similarity of TF-IDF vectors, with IDF fitted on a background corpus."""

    def __init__(self, corpus: list[str]):
        df = Counter(t for doc in corpus for t in set(tokens(doc)))
        n = len(corpus)
        self.idf = {t: math.log((1 + n) / (1 + d)) + 1 for t, d in df.items()}
        self.default = math.log(1 + n) + 1

    def _vec(self, text: str) -> dict[str, float]:
        return {t: c * self.idf.get(t, self.default) for t, c in Counter(tokens(text)).items()}

    def __call__(self, a: str, b: str) -> float:
        va, vb = self._vec(a), self._vec(b)
        dot = sum(w * vb.get(t, 0.0) for t, w in va.items())
        na, nb = math.sqrt(sum(w * w for w in va.values())), math.sqrt(sum(w * w for w in vb.values()))
        return dot / (na * nb) if na and nb else 0.0


def precision_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    top = ranked[:k]
    return sum(1 for r in top if r in relevant) / k if top else 0.0


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    return sum(1 for r in ranked[:k] if r in relevant) / len(relevant) if relevant else 1.0


def reciprocal_rank(ranked: list[str], relevant: set[str]) -> float:
    return next((1 / (i + 1) for i, r in enumerate(ranked) if r in relevant), 0.0)


def percentile(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))] if xs else 0.0
