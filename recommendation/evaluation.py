"""Ranking metrics for one user with one or more relevant products."""

from math import log2


def ranking_metrics(recommendations, targets, k=10):
    targets = set(targets)
    top = list(recommendations)[:k]
    if k < 1 or not targets:
        raise ValueError('Use a positive k and a nonempty target set.')
    if len(top) != len(set(top)):
        raise ValueError('Recommendations must not contain duplicate products.')
    hits = sum(item in targets for item in top)
    dcg = sum(1 / log2(rank + 1) for rank, item in enumerate(top, 1) if item in targets)
    ideal_dcg = sum(1 / log2(rank + 1) for rank in range(1, min(k, len(targets)) + 1))
    return {'hits': hits, f'recall_at_{k}': hits / len(targets), f'ndcg_at_{k}': dcg / ideal_dcg}
