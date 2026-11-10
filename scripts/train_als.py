"""Train a fresh ALS model using the mock dataset's saved training matrix."""

import hashlib
import json
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

import numpy as np
from implicit.cpu.als import AlternatingLeastSquares
from scipy.sparse import load_npz
from threadpoolctl import threadpool_limits


def main():
    root = Path(__file__).resolve().parents[1]
    matrix_dir = root / 'outputs/matrices'
    matrix_path = matrix_dir / 'train_user_items.npz'
    ids_path = matrix_dir / 'train_ids.npz'
    summary = json.loads((matrix_dir / 'summary.json').read_text(encoding='utf-8'))
    train_hash = hashlib.sha256((root / 'data/processed/train.csv').read_bytes()).hexdigest()
    if train_hash != summary['source_sha256']:
        raise ValueError('train.csv has changed. Run scripts.build_interaction_matrix again.')

    user_items = load_npz(matrix_path).tocsr()
    with np.load(ids_path, allow_pickle=False) as ids:
        user_ids, product_ids = ids['user_ids'], ids['product_ids']
    if (user_items.shape != (len(user_ids), len(product_ids))
            or list(user_items.shape) != summary['shape']
            or user_items.nnz != summary['nonzero_entries']
            or user_items.nnz == 0 or not np.all(user_items.data == 1)):
        raise ValueError('Training matrix or ID mappings are inconsistent. Rebuild the matrix.')

    # Starting settings from the Amazon experiment; not yet tuned for mock data.
    settings = dict(factors=128, regularization=0.01, iterations=20,
                    alpha=20, random_state=42, num_threads=4)
    started = perf_counter()
    with threadpool_limits(limits=1, user_api='blas'):
        model = AlternatingLeastSquares(**settings)
        model.fit(user_items, show_progress=False)
    training_seconds = perf_counter() - started
    if not np.isfinite(model.user_factors).all() or not np.isfinite(model.item_factors).all():
        raise ValueError('Training produced non-finite embeddings.')

    output = root / 'outputs/models'
    output.mkdir(parents=True, exist_ok=True)
    model.save(str(output / 'als.npz'))
    np.savez_compressed(output / 'als_ids.npz', user_ids=user_ids, product_ids=product_ids)

    # Verify serialization and a small recommendation call; this is not evaluation.
    restored = AlternatingLeastSquares.load(str(output / 'als.npz'))
    if (not np.array_equal(model.user_factors, restored.user_factors)
            or not np.array_equal(model.item_factors, restored.item_factors)):
        raise ValueError('Reloaded model differs from the trained model.')
    with np.load(output / 'als_ids.npz', allow_pickle=False) as saved_ids:
        if (not np.array_equal(user_ids, saved_ids['user_ids'])
                or not np.array_equal(product_ids, saved_ids['product_ids'])):
            raise ValueError('Reloaded ID mappings differ from the matrix mappings.')
    k = min(10, user_items.shape[1] - user_items[0].nnz)
    with threadpool_limits(limits=1, user_api='blas'):
        items, scores = restored.recommend(0, user_items[0], N=k, filter_already_liked_items=True)
    if (len(set(items)) != k or not np.isfinite(scores).all()
            or any(item < 0 or item >= len(product_ids) for item in items)
            or set(items) & set(user_items[0].indices)):
        raise ValueError('Recommendation smoke check failed.')

    config = {
        'model': 'ALS', 'settings': settings, 'training_seconds': training_seconds,
        'user_embeddings_shape': list(model.user_factors.shape),
        'product_embeddings_shape': list(model.item_factors.shape),
        'training_interactions': user_items.nnz, 'training_csv_sha256': train_hash,
        'matrix_sha256': hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
        'matrix_ids_sha256': hashlib.sha256(ids_path.read_bytes()).hexdigest(),
        'versions': {name: version(name) for name in ('implicit', 'numpy', 'scipy')},
        'status': 'Trained on train only. Validation and test evaluation have not been run.',
        'verification': 'Saved embeddings and mappings reloaded exactly; unseen-item recommendation smoke check passed.',
    }
    (output / 'als_config.json').write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    print(f'User embeddings: {model.user_factors.shape}')
    print(f'Product embeddings: {model.item_factors.shape}')
    print(f'Training time: {training_seconds:.2f} seconds')
    print(f'Saved and verified model and ID mappings: {output}')


if __name__ == '__main__':
    main()
