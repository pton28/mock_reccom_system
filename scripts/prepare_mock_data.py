"""Split whole mock sessions, then build binary user-product interactions."""

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

POSITIVE_EVENTS = {
    'product_click', 'product_view', 'add_to_wishlist', 'add_to_cart', 'purchase',
}
SPLITS = ('train', 'validation', 'test')


def prepare(events):
    # Include impression-only sessions when deciding which sessions are last.
    sessions = {}
    for event in events:
        user, sid = event['distinct_id'], event['session_id']
        if not user or not sid:
            raise ValueError('Every event needs a user ID and session ID.')
        stamp = datetime.fromisoformat(event['timestamp'])
        if stamp.tzinfo is None:
            raise ValueError('Timestamps must include a timezone.')
        stamp = stamp.astimezone(timezone.utc)
        session = sessions.setdefault((user, sid), {'start': stamp, 'end': stamp, 'products': set()})
        session['start'] = min(session['start'], stamp)
        session['end'] = max(session['end'], stamp)
        if event['event_name'] in POSITIVE_EVENTS:
            if not event.get('product_id'):
                raise ValueError('Positive events need a product ID.')
            session['products'].add(event['product_id'])

    by_user = defaultdict(list)
    for (user, sid), session in sessions.items():
        by_user[user].append((sid, session))
    pairs = {name: set() for name in SPLITS}
    assignments, statuses = [], []
    excluded = []
    removed = {'validation': 0, 'test': 0}
    for user, history in sorted(by_user.items()):
        history.sort(key=lambda entry: (entry[1]['start'], entry[0]))
        if len(history) < 3:
            excluded.append(user)
            continue
        # Reject crossing session boundaries rather than leak later events into train.
        train_end = max(session['end'] for _, session in history[:-2])
        if train_end >= history[-2][1]['start'] or history[-2][1]['end'] >= history[-1][1]['start']:
            raise ValueError(f'Overlapping split boundaries for user {user}.')
        products = {name: set() for name in SPLITS}
        for index, (sid, session) in enumerate(history):
            name = 'test' if index == len(history) - 1 else 'validation' if index == len(history) - 2 else 'train'
            products[name].update(session['products'])
            assignments.append((user, sid, name, session['start'].isoformat(), session['end'].isoformat()))
        status = {'user_id': user, 'session_count': len(history), 'train_product_count': len(products['train'])}
        for name in ('validation', 'test'):
            status[f'{name}_positive_count_before_filter'] = len(products[name])
            seen = products[name] & products['train']
            removed[name] += len(seen)
            products[name] -= products['train']
            status[f'{name}_target_count'] = len(products[name])
        statuses.append(status)
        for name in SPLITS:
            pairs[name].update((user, item) for item in products[name])

    train_users = {user for user, _ in pairs['train']}
    train_items = {item for _, item in pairs['train']}
    summary = {
        'positive_events': sorted(POSITIVE_EVENTS),
        'interaction_value': 1,
        'split_policy': 'Per user: earlier sessions=train, second-last=validation, last=test. Order by session start, then ID.',
        'target_policy': 'Unique positive products excluding positive training history; same training history for validation and test.',
        'users_in_source': len(by_user), 'sessions_in_source': len(sessions),
        'users_with_fewer_than_3_sessions': excluded,
        'retained_users': len(statuses),
        'retained_users_without_positive_training_history': len(statuses) - len(train_users),
        'splits': {},
        'notes': [
            'CSV rows are binary positive interactions; repeated events do not increase weight.',
            'Unseen target products and users are retained and reported, not silently removed.',
            'Users with no eligible targets have no holdout CSV rows; see user_evaluation_status.csv.',
            'A validation product may also be a test target: only training positives are excluded.',
            'Per-user chronological splitting does not enforce a common global time cutoff.',
        ],
    }
    for name in SPLITS:
        summary['splits'][name] = {
            'rows': len(pairs[name]), 'users': len({u for u, _ in pairs[name]}),
            'products': len({p for _, p in pairs[name]}),
        }
        if name != 'train':
            summary['splits'][name].update({
                'targets_removed_as_seen_in_training': removed[name],
                'users_without_positive_events_in_session': sum(s[f'{name}_positive_count_before_filter'] == 0 for s in statuses),
                'users_without_eligible_targets': sum(s[f'{name}_target_count'] == 0 for s in statuses),
                'target_rows_with_products_absent_from_training': sum(p not in train_items for _, p in pairs[name]),
                'target_users_absent_from_training': len({u for u, _ in pairs[name]} - train_users),
            })
    return pairs, assignments, statuses, summary


def save_csv(path, columns, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, help='Folder containing generated events.jsonl')
    args = parser.parse_args()
    if args.dataset:
        source = args.dataset / 'events.jsonl'
    else:
        sources = sorted((root / 'data/product-demo-v1/synthetic/raw').glob('*/events.jsonl'))
        if len(sources) != 1:
            parser.error('Specify --dataset when zero or multiple generated datasets are found.')
        source = sources[0]
    digest = hashlib.sha256()
    with source.open('rb') as stream:
        def events():
            for line in stream:
                digest.update(line)
                yield json.loads(line)
        pairs, assignments, statuses, summary = prepare(events())
    summary.update({'source': str(source.resolve()), 'source_sha256': digest.hexdigest()})
    output = root / 'data/processed'
    output.mkdir(parents=True, exist_ok=True)
    for name in SPLITS:
        save_csv(output / f'{name}.csv', ['user_id', 'product_id'], sorted(pairs[name]))
    save_csv(output / 'session_splits.csv', ['user_id', 'session_id', 'split', 'start', 'end'], assignments)
    columns = ['user_id', 'session_count', 'train_product_count',
               'validation_positive_count_before_filter', 'validation_target_count',
               'test_positive_count_before_filter', 'test_target_count']
    save_csv(output / 'user_evaluation_status.csv', columns, ([row[col] for col in columns] for row in statuses))
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))
    print(f'\nSaved splits and reports: {output}')


if __name__ == '__main__':
    main()
