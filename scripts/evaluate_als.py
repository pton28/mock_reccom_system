"""Evaluate ALS and popularity on mock validation data with multiple targets."""

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from implicit.cpu.als import AlternatingLeastSquares
from scipy.sparse import load_npz
from threadpoolctl import threadpool_limits

from recommendation.evaluation import ranking_metrics


def read_csv(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def aggregate(rows):
    return {
        'users': len(rows), 'hits': sum(row['hits'] for row in rows),
        'recall_at_10': sum(row['recall_at_10'] for row in rows) / len(rows) if rows else None,
        'ndcg_at_10': sum(row['ndcg_at_10'] for row in rows) / len(rows) if rows else None,
    }


def evaluate_holdout(root=None, model=None, model_name='als', settings=None, write=True, split='validation'):
    if split not in ('validation', 'test'):
        raise ValueError('Choose validation or test.')
    root = root or Path(__file__).resolve().parents[1]
    models, matrices = root / 'outputs/models', root / 'outputs/matrices'
    config = json.loads((models / f'{model_name}_config.json').read_text(encoding='utf-8'))
    inputs = {
        'training_csv_sha256': root / 'data/processed/train.csv',
        'matrix_sha256': matrices / 'train_user_items.npz',
        'matrix_ids_sha256': matrices / 'train_ids.npz',
    }
    for key, path in inputs.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != config[key]:
            raise ValueError(f'{path.name} changed since training. Rebuild and retrain first.')
    matrix = load_npz(matrices / 'train_user_items.npz').tocsr()
    with np.load(models / f'{model_name}_ids.npz', allow_pickle=False) as ids:
        user_ids, product_ids = ids['user_ids'], ids['product_ids']
    with np.load(matrices / 'train_ids.npz', allow_pickle=False) as ids:
        if not np.array_equal(user_ids, ids['user_ids']) or not np.array_equal(product_ids, ids['product_ids']):
            raise ValueError('Model and matrix mappings differ.')
    user_map = {uid: index for index, uid in enumerate(user_ids)}
    catalog = set(product_ids)
    from_disk = model is None
    if from_disk:
        with threadpool_limits(limits=1, user_api='blas'):
            model = AlternatingLeastSquares.load(str(models / f'{model_name}.npz'))
    model.num_threads = 4
    if model.user_factors.shape[0] != matrix.shape[0] or model.item_factors.shape[0] != matrix.shape[1]:
        raise ValueError('Model dimensions do not match the training matrix.')

    targets = defaultdict(set)
    holdout_path = root / f'data/processed/{split}.csv'
    for row in read_csv(holdout_path):
        if not row.get('user_id') or not row.get('product_id'):
            raise ValueError(f'{split} IDs cannot be missing.')
        targets[row['user_id']].add(row['product_id'])
    if not targets:
        raise ValueError(f'{split} has no eligible users.')
    statuses = read_csv(root / 'data/processed/user_evaluation_status.csv')
    target_count = f'{split}_target_count'
    if {row['user_id']: int(row[target_count]) for row in statuses if int(row[target_count])} != {uid: len(items) for uid, items in targets.items()}:
        raise ValueError(f'{split} and user status report differ. Rerun data preparation.')

    # Popularity counts distinct training users; product ID breaks ties.
    counts = np.asarray(matrix.sum(axis=0)).ravel()
    popular = np.lexsort((product_ids, -counts))
    per_user = []
    with threadpool_limits(limits=1, user_api='blas'):
        for uid, relevant in sorted(targets.items()):
            index = user_map.get(uid)
            seen = set(matrix[index].indices) if index is not None else set()
            if relevant & {product_ids[item] for item in seen}:
                raise ValueError(f'{split} targets overlap training history for {uid}.')
            pop_items = [product_ids[item] for item in popular if item not in seen][:10]
            als_items = []
            if index is not None:
                k = min(10, len(product_ids) - len(seen))
                item_indices, scores = model.recommend(index, matrix[index], N=k, filter_already_liked_items=True)
                if (not np.isfinite(scores).all() or any(item < 0 or item >= len(product_ids) for item in item_indices)
                        or set(item_indices) & seen):
                    raise ValueError('ALS returned invalid recommendations.')
                als_items = product_ids[item_indices].tolist()
            for name, recommendations in [('ALS', als_items), ('popularity', pop_items)]:
                per_user.append({
                    'model': name, 'user_id': uid, 'known_user': index is not None,
                    'target_count': len(relevant), **ranking_metrics(recommendations, relevant),
                })

    results = {}
    for name in ('ALS', 'popularity'):
        rows = [row for row in per_user if row['model'] == name]
        results[name] = {
            'all_users': aggregate(rows),
            'known_users': aggregate([row for row in rows if row['known_user']]),
            'cold_users': aggregate([row for row in rows if not row['known_user']]),
        }
    report = {
        'split': split, 'k': 10,
        'candidate_policy': 'All training products, excluding positive training history.',
        'cold_user_policy': 'ALS returns no recommendations (zero scores). Popularity uses the global training ranking.',
        'averaging': 'Compute Recall and binary NDCG per user, then average equally across users with eligible targets.',
        'users_without_eligible_targets': sum(int(row[target_count]) == 0 for row in statuses),
        'target_products_absent_from_training_rows': sum(item not in catalog for items in targets.values() for item in items),
        f'{split}_sha256': hashlib.sha256(holdout_path.read_bytes()).hexdigest(),
        'model_sha256': hashlib.sha256((models / f'{model_name}.npz').read_bytes()).hexdigest() if from_disk else None,
        'settings': settings or config['settings'], 'results': results,
    }
    if not write:
        return report
    output = root / 'outputs/results'
    output.mkdir(parents=True, exist_ok=True)
    prefix = '' if model_name == 'als' else f'{model_name}_'
    (output / f'{prefix}{split}_metrics.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    with (output / f'{prefix}{split}_per_user.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(per_user[0]))
        writer.writeheader()
        writer.writerows(per_user)
    for name, scores in results.items():
        overall = scores['all_users']
        print(f"{name}: users={overall['users']:,}, Recall@10={overall['recall_at_10']:.6f}, NDCG@10={overall['ndcg_at_10']:.6f}")
    print(f"Cold {split} users: {results['ALS']['cold_users']['users']}")
    print(f"Users without eligible targets: {report['users_without_eligible_targets']}")
    print(f'Saved metrics and per-user results: {output}')
    return report


def evaluate_validation(root=None, model=None, model_name='als', settings=None, write=True):
    return evaluate_holdout(root, model, model_name, settings, write, split='validation')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tuned', action='store_true', help='Evaluate the separately saved tuned model.')
    args = parser.parse_args()
    evaluate_validation(model_name='als_tuned' if args.tuned else 'als')
