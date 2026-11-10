import csv
import hashlib
import json
import tempfile
import unittest
from math import log2
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix, save_npz

from scripts.evaluate_als import evaluate_holdout


class FakeModel:
    user_factors = np.zeros((2, 2))
    item_factors = np.zeros((12, 2))

    def recommend(self, index, history, N, filter_already_liked_items):
        return np.array([1, 3, 2]), np.array([3., 2., 1.])


class HoldoutEvaluationTests(unittest.TestCase):
    def test_test_targets_multi_target_scores_and_cold_user_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ('data/processed', 'outputs/models', 'outputs/matrices'):
                (root / folder).mkdir(parents=True)

            def write_csv(name, columns, rows):
                with (root / 'data/processed' / name).open('w', newline='') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(columns)
                    writer.writerows(rows)

            users = np.array(['a', 'b'])
            products = np.array([f'p{i:02}' for i in range(12)])
            matrix = csr_matrix((np.ones(12), ([0] + [1] * 11, list(range(12)))), shape=(2, 12))
            save_npz(root / 'outputs/matrices/train_user_items.npz', matrix)
            for name in ('outputs/matrices/train_ids.npz', 'outputs/models/als_ids.npz'):
                np.savez(root / name, user_ids=users, product_ids=products)
            write_csv('train.csv', ['user_id', 'product_id'], [('a', 'p00')])
            # This validation target would overlap training; test must read its own file.
            write_csv('validation.csv', ['user_id', 'product_id'], [('a', 'p00')])
            write_csv('test.csv', ['user_id', 'product_id'], [('a', 'p01'), ('a', 'p02'), ('cold', 'p03')])
            write_csv('user_evaluation_status.csv', ['user_id', 'validation_target_count', 'test_target_count'],
                      [('a', 1, 2), ('cold', 0, 1), ('empty', 0, 0)])
            config = {'settings': {}}
            for key, path in [('training_csv_sha256', 'data/processed/train.csv'),
                              ('matrix_sha256', 'outputs/matrices/train_user_items.npz'),
                              ('matrix_ids_sha256', 'outputs/matrices/train_ids.npz')]:
                config[key] = hashlib.sha256((root / path).read_bytes()).hexdigest()
            (root / 'outputs/models/als_config.json').write_text(json.dumps(config))
            report = evaluate_holdout(root, model=FakeModel(), split='test', write=False)
            overall = report['results']['ALS']['all_users']
            self.assertEqual(report['split'], 'test')
            self.assertIn('test_sha256', report)
            self.assertEqual(overall['users'], 2)
            self.assertEqual(overall['hits'], 2)
            self.assertEqual(overall['recall_at_10'], .5)
            self.assertAlmostEqual(overall['ndcg_at_10'], (1.5 / (1 + 1 / log2(3))) / 2)
            self.assertEqual(report['results']['ALS']['cold_users']['users'], 1)
            self.assertEqual(report['users_without_eligible_targets'], 1)
            self.assertEqual(report['results']['popularity']['all_users']['recall_at_10'], 1)


if __name__ == '__main__':
    unittest.main()
