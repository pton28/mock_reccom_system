import unittest
from math import log2

from recommendation.evaluation import ranking_metrics


class RankingMetricsTests(unittest.TestCase):
    def test_multiple_targets_and_rank_discount(self):
        scores = ranking_metrics(['a', 'x', 'b'], {'a', 'b', 'c'})
        self.assertEqual(scores['hits'], 2)
        self.assertAlmostEqual(scores['recall_at_10'], 2 / 3)
        self.assertAlmostEqual(scores['ndcg_at_10'], 1.5 / (1 + 1 / log2(3) + .5))

    def test_targets_beyond_k_still_count_in_recall(self):
        scores = ranking_metrics(list(range(11)), set(range(20)))
        self.assertEqual(scores['hits'], 10)
        self.assertEqual(scores['recall_at_10'], .5)
        self.assertEqual(scores['ndcg_at_10'], 1)

    def test_no_recommendations_and_unseen_target(self):
        self.assertEqual(ranking_metrics([], {'unseen'})['ndcg_at_10'], 0)
        self.assertEqual(ranking_metrics(['a'], {'a', 'unseen'})['recall_at_10'], .5)

    def test_invalid_recommendations_or_targets(self):
        with self.assertRaises(ValueError):
            ranking_metrics(['a', 'a'], {'a'})
        with self.assertRaises(ValueError):
            ranking_metrics(['a'], set())


if __name__ == '__main__':
    unittest.main()
