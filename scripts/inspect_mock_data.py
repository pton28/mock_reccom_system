"""Inspect generated mock events without changing them (standard library only)."""

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from uuid import UUID


def inspect(dataset, catalog):
    users = {row['id'] for row in json.loads((catalog / 'users.json').read_text(encoding='utf-8'))}
    products = {row['id'] for row in json.loads((catalog / 'products.json').read_text(encoding='utf-8'))}
    event_types = ['product_impression', 'product_click', 'product_view', 'search',
                   'add_to_wishlist', 'add_to_cart', 'remove_from_cart', 'purchase']
    actions = {'product_click', 'product_view', 'add_to_wishlist', 'add_to_cart', 'purchase'}
    counts, issues, missing = Counter(), Counter(), Counter()
    for key in ['invalid_json_records', 'invalid_event_id_format',
                'timestamps_without_timezone', 'unparseable_timestamps']:
        issues[key] = 0
    fields, event_ids, pairs, action_pairs, active_users, active_products = set(), set(), set(), set(), set(), set()
    user_products, user_actions, user_sessions = defaultdict(set), defaultdict(set), defaultdict(set)
    session_users, last_time = defaultdict(set), {}
    earliest = latest = None
    rows = product_events = action_events = 0
    required = ['event_id', 'distinct_id', 'event_name', 'timestamp', 'session_id']

    with (dataset / 'events.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            rows += 1
            try:
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError('Expected an object')
            except ValueError:
                issues['invalid_json_records'] += 1
                continue
            fields.update(event)
            for key in required:
                missing[key] += event.get(key) is None or event.get(key) == ''
            uid, pid, sid = event.get('distinct_id'), event.get('product_id'), event.get('session_id')
            name, eid = event.get('event_name'), event.get('event_id')
            counts[str(name)] += 1
            issues['unknown_event_types'] += name not in event_types
            issues['unknown_user_references'] += uid is not None and uid not in users
            issues['unknown_product_references'] += pid is not None and pid not in products
            issues['missing_product_for_product_event'] += name != 'search' and not pid
            issues['missing_query_for_search'] += name == 'search' and not str(event.get('query') or '').strip()
            issues['missing_order_id_for_purchase'] += name == 'purchase' and not event.get('order_id')
            issues['missing_order_item_id_for_purchase'] += name == 'purchase' and not event.get('order_item_id')
            if eid:
                issues['duplicate_event_ids'] += eid in event_ids
                event_ids.add(eid)
                try:
                    UUID(str(eid))
                except ValueError:
                    issues['invalid_event_id_format'] += 1
            if uid:
                active_users.add(uid)
            if pid:
                active_products.add(pid)
            if uid and pid:
                product_events += 1
                pairs.add((uid, pid))
                user_products[uid].add(pid)
                if name in actions:
                    action_events += 1
                    action_pairs.add((uid, pid))
                    user_actions[uid].add(pid)
            if uid and sid:
                user_sessions[uid].add(sid)
                session_users[sid].add(uid)
            try:
                stamp = datetime.fromisoformat(event['timestamp'])
                if stamp.tzinfo is None:
                    issues['timestamps_without_timezone'] += 1
                    continue
                stamp = stamp.astimezone(timezone.utc)
            except (KeyError, ValueError, TypeError):
                issues['unparseable_timestamps'] += 1
                continue
            earliest = min(earliest, stamp) if earliest else stamp
            latest = max(latest, stamp) if latest else stamp
            if sid:
                issues['non_increasing_timestamps_within_session'] += sid in last_time and stamp <= last_time[sid]
                last_time[sid] = stamp

    def distribution(mapping):
        values = [len(mapping[uid]) for uid in sorted(users)]
        return {'min': min(values), 'median': median(values), 'max': max(values),
                'users_with_zero': sum(v == 0 for v in values),
                'users_with_fewer_than_3': sum(v < 3 for v in values)} if values else {}

    issues['sessions_with_multiple_users'] = sum(len(value) > 1 for value in session_users.values())
    action_products = {pid for _, pid in action_pairs}
    return {
        'dataset': str(dataset), 'rows': rows, 'fields': sorted(fields),
        'catalog_users': len(users), 'active_users': len(active_users),
        'catalog_products': len(products), 'products_with_events': len(active_products),
        'sessions': len(session_users),
        'event_counts': {name: counts[name] for name in sorted(set(event_types) | set(counts))},
        'missing_required_fields': dict(missing), 'issues': dict(sorted(issues.items())),
        'earliest_timestamp': earliest.isoformat() if earliest else None,
        'latest_timestamp': latest.isoformat() if latest else None,
        'unique_user_product_pairs_all_events': len(pairs),
        'repeated_user_product_rows_all_events': product_events - len(pairs),
        'action_events': action_events, 'unique_action_user_product_pairs': len(action_pairs),
        'repeated_action_user_product_rows': action_events - len(action_pairs),
        'products_without_actions': len(products - action_products),
        'distinct_products_per_user_all_events': distribution(user_products),
        'distinct_action_products_per_user': distribution(user_actions),
        'sessions_per_user': distribution(user_sessions),
        'notes': [
            'Per-user distributions include all catalog users, including those with zero activity.',
            'Actions here are click, view, wishlist, cart addition and purchase; these counts are not training weights.',
            'Repeated user-product pairs are expected. Click and its following view should not be blindly double-weighted.',
            'Session ID is required for the planned session-based split, although optional in the backend schema.',
            'This inspection checks basic fields, references, duplicates and times; it is not full backend schema validation.',
        ],
    }


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    data = root / 'data/product-demo-v1'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, help='Folder containing generated events.jsonl')
    args = parser.parse_args()
    datasets = [args.dataset] if args.dataset else sorted((data / 'synthetic/raw').glob('*/events.jsonl'))
    if len(datasets) != 1:
        parser.error('Specify --dataset when zero or multiple generated datasets are found.')
    dataset = args.dataset if args.dataset else datasets[0].parent
    report = inspect(dataset, data / 'mock')
    output = root / 'outputs/results/mock_data_inspection.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    print(f'\nSaved report: {output}')
