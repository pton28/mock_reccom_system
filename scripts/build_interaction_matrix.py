"""Build a binary CSR matrix and ordered ID mappings from train.csv only."""

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix, load_npz, save_npz


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / 'data/processed/train.csv'
    with source.open(encoding='utf-8', newline='') as stream:
        train = list(csv.DictReader(stream))
    if not train or any(not row.get('user_id') or not row.get('product_id') for row in train):
        raise ValueError('Training data must contain nonempty user_id and product_id fields.')

    # Each array position is the corresponding matrix row or column index.
    user_ids = np.array(sorted({row['user_id'] for row in train}))
    product_ids = np.array(sorted({row['product_id'] for row in train}))
    user_map = {uid: index for index, uid in enumerate(user_ids)}
    product_map = {pid: index for index, pid in enumerate(product_ids)}
    rows = [user_map[row['user_id']] for row in train]
    columns = [product_map[row['product_id']] for row in train]
    matrix = csr_matrix(
        (np.ones(len(train), dtype=np.float32), (rows, columns)),
        shape=(len(user_ids), len(product_ids)),
    )
    matrix.data[:] = 1  # Repeated input pairs still represent one positive.

    output = root / 'outputs/matrices'
    output.mkdir(parents=True, exist_ok=True)
    save_npz(output / 'train_user_items.npz', matrix)
    np.savez_compressed(output / 'train_ids.npz', user_ids=user_ids, product_ids=product_ids)

    # Reload the artifacts and check every saved entry against the source CSV.
    saved = load_npz(output / 'train_user_items.npz')
    with np.load(output / 'train_ids.npz', allow_pickle=False) as ids:
        saved_users, saved_products = ids['user_ids'], ids['product_ids']
    saved_rows, saved_columns = saved.nonzero()
    actual = set(zip(saved_users[saved_rows], saved_products[saved_columns]))
    expected = {(row['user_id'], row['product_id']) for row in train}
    if (actual != expected or not np.all(saved.data == 1)
            or saved.shape != (len(saved_users), len(saved_products))
            or saved.nnz != len(expected)
            or not np.array_equal(user_ids, saved_users)
            or not np.array_equal(product_ids, saved_products)):
        raise ValueError('Saved matrix or mappings do not match training data.')

    summary = {
        'source': 'data/processed/train.csv',
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'shape': list(matrix.shape), 'nonzero_entries': matrix.nnz,
        'format': matrix.format, 'dtype': str(matrix.dtype), 'interaction_value': 1,
        'density': matrix.nnz / (matrix.shape[0] * matrix.shape[1]),
        'mapping': 'user_ids[i] identifies row i; product_ids[j] identifies column j.',
        'verification': 'Reloaded matrix and mappings exactly match the training pairs.',
    }
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(f'Matrix shape: {matrix.shape}')
    print(f'Positive interactions: {matrix.nnz:,}')
    print(f'Format: {matrix.format}; dtype: {matrix.dtype}')
    print(f'Saved and verified matrix and ID mappings: {output}')


if __name__ == '__main__':
    main()
