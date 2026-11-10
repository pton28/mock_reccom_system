"""Freeze the selected seed-42 ALS model, then evaluate the test split once."""

import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from scripts.evaluate_als import evaluate_holdout


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_model(root):
    models = root / 'outputs/models'
    selection_path = models / 'als_final_selection.json'
    if selection_path.exists():
        selection = json.loads(selection_path.read_text(encoding='utf-8'))
        for relative, expected in selection['artifact_hashes'].items():
            if sha256(root / relative) != expected:
                raise ValueError(f'Frozen artifact changed: {relative}')
        return selection

    seeds = json.loads((root / 'outputs/results/als_seed_summary.json').read_text(encoding='utf-8'))
    config = json.loads((models / 'als_tuned_config.json').read_text(encoding='utf-8'))
    if (set(seeds['seeds']) != {42, 7, 123}
            or not seeds['tuned_improves_ndcg_at_every_seed']
            or any(row['ndcg_gain'] <= 0 for row in seeds['paired_comparisons'])
            or config['settings'] != seeds['settings']['tuned']
            or config['settings']['random_state'] != 42):
        raise ValueError('The chosen configuration does not match the successful seed comparison.')
    if sha256(models / 'als_tuned.npz') != seeds['model_hashes']['tuned']:
        raise ValueError('Tuned model changed after the seed comparison.')
    if sha256(root / 'data/processed/validation.csv') != seeds['validation_sha256']:
        raise ValueError('Validation data changed after model selection.')
    if config['training_csv_sha256'] != seeds['training_csv_sha256']:
        raise ValueError('Training data differs from the seed comparison.')
    inputs = {
        'data/processed/train.csv': config['training_csv_sha256'],
        'data/processed/validation.csv': seeds['validation_sha256'],
        'outputs/matrices/train_user_items.npz': config['matrix_sha256'],
        'outputs/matrices/train_ids.npz': config['matrix_ids_sha256'],
    }
    for relative, expected in inputs.items():
        if sha256(root / relative) != expected:
            raise ValueError(f'Training/selection artifact changed: {relative}')
    for name in ('als_final.npz', 'als_final_ids.npz', 'als_final_config.json'):
        if (models / name).exists():
            raise FileExistsError(f'Unrecorded final artifact already exists: {name}')
    shutil.copyfile(models / 'als_tuned.npz', models / 'als_final.npz')
    shutil.copyfile(models / 'als_tuned_ids.npz', models / 'als_final_ids.npz')
    config['status'] = 'Frozen before test evaluation; train-only history, seed 42.'
    (models / 'als_final_config.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    for name in ('als_final.npz', 'als_final_ids.npz', 'als_final_config.json'):
        inputs[f'outputs/models/{name}'] = sha256(models / name)
    selection = {
        'frozen_at_utc': datetime.now(timezone.utc).isoformat(),
        'settings': config['settings'],
        'selection_basis': 'Highest validation NDCG in the grid; improvement verified at seeds 42, 7, 123.',
        'history_policy': 'Train only. No refit on validation; test excludes training positives only.',
        'seed_policy': 'Retain previously chosen seed 42; do not choose a seed using test results.',
        'artifact_hashes': inputs,
    }
    selection_path.write_text(json.dumps(selection, indent=2) + '\n', encoding='utf-8')
    return selection


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / 'outputs/results'
    if (output / 'als_final_test_metrics.json').exists():
        raise FileExistsError('Test results already exist; inspect outputs/results/als_final_test_metrics.json.')
    # Persist the decision before the evaluator opens test.csv.
    selection = freeze_model(root)
    report = evaluate_holdout(root, model_name='als_final', split='test')
    report['selection'] = selection
    (output / 'als_final_test_metrics.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    rows = [{'model': name, **scores['all_users']} for name, scores in report['results'].items()]
    with (output / 'final_test_comparison.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print('Final test complete. Model settings were frozen before test evaluation.')


if __name__ == '__main__':
    main()
