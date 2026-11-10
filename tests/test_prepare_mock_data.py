import unittest

from scripts.prepare_mock_data import prepare


def event(user, session, day, product, action='product_click', second=0):
    return {'distinct_id': user, 'session_id': session, 'product_id': product,
            'event_name': action, 'timestamp': f'2026-01-{day:02d}T00:00:{second:02d}+00:00'}


class PrepareMockDataTests(unittest.TestCase):
    def test_whole_sessions_binary_pairs_and_multiple_targets(self):
        events = [
            event('u', 's1', 1, 'a'), event('u', 's1', 1, 'a', 'product_view', 1),
            event('u', 's2', 2, 'a'), event('u', 's2', 2, 'b', second=1),
            event('u', 's2', 2, 'c', second=2),
            event('u', 's3', 3, 'a'), event('u', 's3', 3, 'b', second=1),
            event('u', 's3', 3, 'd', 'product_impression', 2),
        ]
        pairs, assignments, statuses, summary = prepare(reversed(events))
        self.assertEqual(pairs['train'], {('u', 'a')})
        self.assertEqual(pairs['validation'], {('u', 'b'), ('u', 'c')})
        self.assertEqual(pairs['test'], {('u', 'b')})
        self.assertEqual([row[2] for row in assignments], ['train', 'validation', 'test'])
        self.assertEqual(statuses[0]['validation_target_count'], 2)
        self.assertEqual(summary['splits']['validation']['target_rows_with_products_absent_from_training'], 2)

    def test_empty_sessions_are_not_skipped_and_cold_users_are_reported(self):
        events = [event('u', 's1', 1, 'a', 'product_impression'),
                  event('u', 's2', 2, 'b'),
                  event('u', 's3', 3, 'c', 'product_impression'),
                  event('short', 'only', 1, 'a')]
        pairs, _, statuses, summary = prepare(events)
        self.assertEqual(pairs['train'], set())
        self.assertEqual(pairs['validation'], {('u', 'b')})
        self.assertEqual(pairs['test'], set())
        self.assertEqual(summary['users_with_fewer_than_3_sessions'], ['short'])
        self.assertEqual(summary['splits']['validation']['target_users_absent_from_training'], 1)
        self.assertEqual(summary['splits']['test']['users_without_eligible_targets'], 1)
        self.assertEqual(statuses[0]['session_count'], 3)

    def test_overlapping_split_boundaries_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            prepare([event('u', 's1', 1, 'a'), event('u', 's1', 4, 'a'),
                     event('u', 's2', 2, 'b'), event('u', 's3', 3, 'c')])


if __name__ == '__main__':
    unittest.main()
