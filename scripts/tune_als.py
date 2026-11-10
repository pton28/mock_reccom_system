"""Tune mock ALS on validation only; retain the original model and test split."""

import csv
import hashlib
import json
import shutil
from itertools import product
from pathlib import Path
from time import perf_counter

import numpy as np
from implicit.cpu.als import AlternatingLeastSquares
from scipy.sparse import load_npz
from threadpoolctl import threadpool_limits

from scripts.evaluate_als import evaluate_validation


def main():
    root = Path(__file__).resolve().parents[1]
    models, results = root / 'outputs/models', root / 'outputs/results'
    config = json.loads((models / 'als_config.json').read_text(encoding='utf-8'))
    # Reuse exactly the established validation protocol, including cold-user zeros.
    baseline = evaluate_validation(root, write=False)
    baseline_metrics = baseline['results']['ALS']['all_users']
    recorded = json.loads((results / 'validation_metrics.json').read_text(encoding='utf-8'))
    if baseline['validation_sha256'] != recorded['validation_sha256'] or baseline_metrics != recorded['results']['ALS']['all_users']:
        raise ValueError('Baseline results changed. Review the data and evaluation before tuning.')
    matrix = load_npz(root / 'outputs/matrices/train_user_items.npz').tocsr()
    baseline_paths = [models / 'als.npz', models / 'als_ids.npz', models / 'als_config.json', results / 'validation_metrics.json']
    original_hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in baseline_paths}
    trials = []
    best = {'settings': config['settings'], 'metrics': baseline_metrics, 'trial': 0}
    for source, target in [('als.npz', 'als_tuned.npz'), ('als_ids.npz', 'als_tuned_ids.npz')]:
        shutil.copyfile(models / source, models / target)
    best_config = {**config, 'selection_metric': 'validation NDCG@10',
                   'validation_sha256': baseline['validation_sha256'], 'metrics': baseline_metrics,
                   'selected_trial': 0, 'status': 'Selected on validation; test not evaluated.'}

    def save_best_config():
        (models / 'als_tuned_config.json').write_text(json.dumps(best_config, indent=2) + '\n', encoding='utf-8')

    save_best_config()

    def run_trial(settings, stage):
        nonlocal best, best_config
        number = len(trials) + 1
        started = perf_counter()
        reused = settings == config['settings']
        if reused:
            metrics = baseline_metrics
            training_seconds = config['training_seconds']
        else:
            with threadpool_limits(limits=1, user_api='blas'):
                model = AlternatingLeastSquares(**settings)
                model.fit(matrix, show_progress=False)
            training_seconds = perf_counter() - started
            if not np.isfinite(model.user_factors).all() or not np.isfinite(model.item_factors).all():
                raise ValueError(f'Trial {number} produced invalid embeddings.')
            report = evaluate_validation(root, model=model, settings=settings, write=False)
            metrics = report['results']['ALS']['all_users']
        trials.append({'trial': number, 'stage': stage, **settings, **metrics,
                       'reused_baseline': reused, 'training_seconds': training_seconds,
                       'elapsed_seconds': perf_counter() - started})
        with (results / 'als_tuning.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(trials[0]))
            writer.writeheader()
            writer.writerows(trials)
        # Strict ties retain the current selection, including the original baseline.
        if metrics['ndcg_at_10'] > best['metrics']['ndcg_at_10']:
            best = {'settings': settings, 'metrics': metrics, 'trial': number}
            model.save(str(models / 'als_tuned.npz'))
            best_config = {**best_config, 'settings': settings, 'training_seconds': training_seconds,
                           'user_embeddings_shape': list(model.user_factors.shape),
                           'product_embeddings_shape': list(model.item_factors.shape),
                           'metrics': metrics, 'selected_trial': number}
            save_best_config()
        print(f"Trial {number}/50 ({stage}): factors={settings['factors']}, reg={settings['regularization']}, "
              f"alpha={settings['alpha']}, iterations={settings['iterations']} -> "
              f"Recall@10={metrics['recall_at_10']:.6f}, NDCG@10={metrics['ndcg_at_10']:.6f}", flush=True)

    for factors, regularization, alpha in product([16, 32, 64, 128], [0.01, 0.1, 1.0], [1, 5, 20, 50]):
        run_trial(dict(factors=factors, regularization=regularization, alpha=alpha,
                       iterations=20, random_state=42, num_threads=4), 'grid')
    grid_best = best['settings'].copy()
    for iterations in (40, 80):
        run_trial({**grid_best, 'iterations': iterations}, 'iterations')

    # Load and evaluate the saved winner independently of the in-memory trial.
    verified = evaluate_validation(root, model_name='als_tuned')
    if verified['results']['ALS']['all_users'] != best['metrics']:
        raise ValueError('Saved winner did not reproduce the selected metrics.')
    if best['metrics']['ndcg_at_10'] != max(baseline_metrics['ndcg_at_10'], *(row['ndcg_at_10'] for row in trials)):
        raise ValueError('Selection does not match the highest validation NDCG.')
    if any(hashlib.sha256(path.read_bytes()).hexdigest() != digest for path, digest in original_hashes.items()):
        raise ValueError('An original baseline artifact was changed.')
    comparison = {
        'trials': len(trials), 'selection_metric': 'validation NDCG@10',
        'baseline': baseline_metrics, 'tuned': best['metrics'], 'best_settings': best['settings'],
        'recall_relative_improvement': best['metrics']['recall_at_10'] / baseline_metrics['recall_at_10'] - 1,
        'ndcg_relative_improvement': best['metrics']['ndcg_at_10'] / baseline_metrics['ndcg_at_10'] - 1,
        'validation_sha256': baseline['validation_sha256'], 'model_sha256': verified['model_sha256'],
        'verification': 'Saved winner reproduced selected metrics; original baseline files preserved.',
        'notes': 'One seed (42). Iteration sweep applies to the best grid configuration. Test not evaluated.',
    }
    (results / 'als_tuning_summary.json').write_text(json.dumps(comparison, indent=2) + '\n', encoding='utf-8')
    print('\nTuning complete. Best settings:', best['settings'], flush=True)
    print(f"NDCG improvement: {comparison['ndcg_relative_improvement']:.1%}", flush=True)


if __name__ == '__main__':
    main()
