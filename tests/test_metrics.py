from evaluation import metrics


def test_text_metrics_identical_and_disjoint():
    assert metrics.bleu("the pool is exhausted", "the pool is exhausted") > 0.99
    assert metrics.rouge_l("a b c", "a b c") == 1.0
    assert metrics.rouge_n("a b c", "x y z") == 0.0
    sim = metrics.TfidfSimilarity(["pool exhausted", "tls expired"])
    assert sim("pool exhausted", "pool exhausted") > 0.99
    assert sim("pool exhausted", "tls expired") < 0.1


def test_ranking_metrics():
    ranked, rel = ["a", "x", "b"], {"a", "b"}
    assert metrics.precision_at_k(ranked, rel, 3) == 2 / 3
    assert metrics.recall_at_k(ranked, rel, 1) == 0.5
    assert metrics.reciprocal_rank(["x", "a"], rel) == 0.5
