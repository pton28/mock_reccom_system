"""Compare original and tuned ALS at seeds 42, 7 and 123 on validation only."""

import csv
import hashlib
import json
from pathlib import Path
from statistics import mean, stdev
from time import perf_counter

import numpy as np
from implicit.cpu.als import AlternatingLeastSquares
from scipy.sparse import load_npz
from threadpoolctl import threadpool_limits

from scripts.evaluate_als import evaluate_validation


def main():
    root = Path(__file__).resolve().parents[1]
    models, output = root / 'outputs/models', root / 'outputs/results'
    names = {'original': 'als', 'tuned': 'als_tuned'}
    rows, configs, reference = [], {}, {}
    protected = list(models.glob('als*.npz')) + list(models.glob('als*_config.json'))
    hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}

    def record(label, settings, metrics, reused, seconds):
        rows.append({'configuration': label, **settings, **metrics,
                     'reused_saved_model': reused, 'elapsed_seconds': seconds})
        with (output / 'als_seed_comparison.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"{label}, seed={settings['random_state']}: "
              f"Recall@10={metrics['recall_at_10']:.6f}, NDCG@10={metrics['ndcg_at_10']:.6f}", flush=True)

    # Verify saved seed-42 results before reusing them; do not overwrite models.
    for label, name in names.items():
        config = json.loads((models / f'{name}_config.json').read_text(encoding='utf-8'))
        configs[label] = config
        if config['settings']['random_state'] != 42:
            raise ValueError('Expected the previously selected seed-42 models.')
        report = evaluate_validation(root, model_name=name, write=False)
        filename = 'validation_metrics.json' if label == 'original' else 'als_tuned_validation_metrics.json'
        saved = json.loads((output / filename).read_text(encoding='utf-8'))
        for key in ('validation_sha256', 'model_sha256', 'settings', 'results'):
            if report[key] != saved[key]:
                raise ValueError(f'{label}: saved validation results no longer match.')
        reference[label] = report
        record(label, config['settings'], report['results']['ALS']['all_users'], True, 0)
    for key in ('training_csv_sha256', 'matrix_sha256', 'matrix_ids_sha256'):
        if configs['original'][key] != configs['tuned'][key]:
            raise ValueError('Original and tuned models must use identical training inputs.')
    if reference['original']['validation_sha256'] != reference['tuned']['validation_sha256']:
        raise ValueError('Validation data differs between configurations.')

    matrix = load_npz(root / 'outputs/matrices/train_user_items.npz').tocsr()
    for seed in (7, 123):
        for label, name in names.items():
            settings = {**configs[label]['settings'], 'random_state': seed}
            started = perf_counter()
            with threadpool_limits(limits=1, user_api='blas'):
                model = AlternatingLeastSquares(**settings)
                model.fit(matrix, show_progress=False)
            if not np.isfinite(model.user_factors).all() or not np.isfinite(model.item_factors).all():
                raise ValueError(f'Invalid embeddings for {label}, seed={seed}.')
            report = evaluate_validation(root, model=model, model_name=name, settings=settings, write=False)
            record(label, settings, report['results']['ALS']['all_users'], False, perf_counter() - started)

    averages = {}
    for label in names:
        group = [row for row in rows if row['configuration'] == label]
        averages[label] = {'seeds': len(group)}
        for metric in ('recall_at_10', 'ndcg_at_10'):
            values = [row[metric] for row in group]
            averages[label][f'{metric}_mean'] = mean(values)
            averages[label][f'{metric}_std'] = stdev(values)
    paired = []
    for seed in (42, 7, 123):
        scores = {row['configuration']: row for row in rows if row['random_state'] == seed}
        paired.append({'seed': seed,
                       'recall_gain': scores['tuned']['recall_at_10'] - scores['original']['recall_at_10'],
                       'ndcg_gain': scores['tuned']['ndcg_at_10'] - scores['original']['ndcg_at_10']})
    summary = {
        'split': 'validation', 'seeds': [42, 7, 123], 'averages': averages, 'paired_comparisons': paired,
        'tuned_improves_ndcg_at_every_seed': all(row['ndcg_gain'] > 0 for row in paired),
        'tuned_improves_recall_at_every_seed': all(row['recall_gain'] > 0 for row in paired),
        'validation_sha256': reference['original']['validation_sha256'],
        'training_csv_sha256': configs['original']['training_csv_sha256'],
        'model_hashes': {label: reference[label]['model_sha256'] for label in names},
        'settings': {label: configs[label]['settings'] for label in names},
        'protocol': {'candidate_policy': reference['original']['candidate_policy'],
                     'cold_user_policy': reference['original']['cold_user_policy'],
                     'users_without_eligible_targets': reference['original']['users_without_eligible_targets']},
        'notes': 'Standard deviation is across seeds, not a confidence interval. Seed 42 retained; no seed selection. Test not evaluated.',
    }
    if any(hashlib.sha256(path.read_bytes()).hexdigest() != digest for path, digest in hashes.items()):
        raise ValueError('An existing model artifact changed during the comparison.')
    (output / 'als_seed_summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print('\nValidation averages:', json.dumps(averages, indent=2))
    print(f"Tuned improves both metrics at every seed: {all(row['recall_gain'] > 0 and row['ndcg_gain'] > 0 for row in paired)}")
    print(f'Saved seed comparison and summary: {output}')


if __name__ == '__main__':
    main()
