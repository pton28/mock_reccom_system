"""Reproducible exposure -> click -> view -> cart -> purchase sessions."""
import argparse
import hashlib
import json
import random
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

import pandas as pd
from backend.db import records, save_events
from backend.settings import ROOT, layer
from backend.observability import audit
from pipeline.storage import write_parquet


def simulate_sessions(users, products, count=100000, seed=42, scenario="S1_long_term"):
    cfg = json.loads((ROOT / 'configs/simulator.json').read_text())
    if scenario not in cfg['scenarios'] or count < 0:
        raise ValueError('Invalid scenario/count')
    rng = random.Random(seed)
    products = sorted([p for p in products if p['stock'] > 0], key=lambda p: p['id'])
    if not users or not products:
        raise ValueError('Seed catalog/users first')
    # Only identity affects simulation; ignore every legacy user attribute.
    users = [{'id': u['id']} for u in sorted(users, key=lambda u: u['id'])]
    item_ids = [p['id'] for p in products]
    preferences = {u['id']: random.Random(f"{seed}:{u['id']}").sample(item_ids, max(1, len(item_ids) // 5)) for u in users}
    dataset_key = hashlib.sha256(json.dumps({'config':cfg, 'count':count, 'seed':seed, 'scenario':scenario,
                                            'users':users, 'products':products},sort_keys=True).encode()).hexdigest()[:20]
    # Reserve final 10% of products as metadata-only cold items.
    exposed_pool = products[:max(1, int(len(products) * .9))]
    active_users = users[:max(1, int(len(users) * .9))] if scenario == 'S3_cold_start' else users
    start = datetime.fromisoformat(cfg['start'])
    emitted, session_num = 0, 0
    while emitted < count:
        session_num += 1
        estimated_sessions = max(1, count / (cfg['exposure_size'] + 6))
        day = min(cfg['days'] - 1, int((session_num - 1) * cfg['days'] / estimated_sessions))
        session_users = users if scenario == 'S3_cold_start' and day >= cfg['days']*.7 else active_users
        session_pool = products if scenario == 'S3_cold_start' and day >= cfg['days']*.7 else exposed_pool
        user = session_users[(session_num - 1) % len(session_users)]
        sid = str(uuid5(NAMESPACE_URL, f"{cfg['version']}:{dataset_key}:session:{session_num}"))
        ts = start + timedelta(days=day, hours=8 + rng.randrange(12), minutes=rng.randrange(60))
        preferred_items = preferences[user['id']]
        alternatives = [pid for pid in item_ids if pid not in preferred_items]
        shifted = random.Random(f"{seed}:{user['id']}:shift").sample(alternatives, min(len(preferred_items), len(alternatives)))
        intent_items = shifted if scenario == 'S2_intent_shift' and day >= cfg['days']*.65 else preferred_items
        # Per-session intent can differ from long-term taste; hidden values never enter events.
        if rng.random() < .15:
            intent_items = rng.sample(item_ids, max(1, len(item_ids) // 5))
        budget = rng.uniform(500, 1800)
        pool = rng.sample(session_pool, min(cfg['exposure_size'] * 3, len(session_pool)))
        weights = [cfg['exploration'] + int(p['id'] in intent_items) for p in pool]
        exposure = []
        while pool and len(exposure) < cfg['exposure_size']:
            index = rng.choices(range(len(pool)), weights=weights)[0]
            exposure.append(pool.pop(index)); weights.pop(index)
        planned = []
        for position, p in enumerate(exposure, 1):
            planned.append(('product_impression', p, position, None))
            relevance = int(p['id'] in intent_items)
            affordable = min(1, budget / max(p['price'], 1))
            probability = (cfg['noise_click'] + .7 * relevance * affordable) / (1 + .08 * (position - 1))
            if rng.random() < probability:
                planned.extend([('product_click', p, position, None), ('product_view', p, position, None)])
                if rng.random() < cfg['wishlist_probability']:
                    planned.append(('add_to_wishlist', p, position, None))
                if rng.random() < cfg['cart_probability'] * affordable:
                    planned.append(('add_to_cart', p, position, None))
                    if rng.random() < cfg['purchase_probability']:
                        planned.append(('purchase', p, position, f'{sid}:order'))
        for step, (name, p, position, order) in enumerate(planned):
            if emitted >= count:
                break
            ts += timedelta(seconds=rng.randint(3, 50))
            eid = str(uuid5(NAMESPACE_URL, f'{sid}:{step}'))
            yield {'event_id': eid, 'timestamp': ts.isoformat(), 'distinct_id': user['id'], 'session_id': sid,
                   'event_name': name, 'product_id': p['id'], 'source': 'simulator', 'synthetic': True,
                   'environment': 'dev', 'position': position, 'order_id': order,
                   'order_item_id': f'{order}:{p["id"]}' if order else None}
            emitted += 1


def generate(count=100000, seed=42, scenario='S1_long_term', send=False):
    from data_generator.seed import seed as seed_catalog
    seed_catalog()
    events = list(simulate_sessions(records('users'), records('products'), count, seed, scenario))
    payload = '\n'.join(json.dumps(e, sort_keys=True) for e in events)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    out = layer('raw', 'synthetic') / f'{scenario}-{seed}-{digest[:12]}'
    out.mkdir(exist_ok=True)
    (out / 'events.jsonl').write_text(payload, encoding='utf-8')
    write_parquet(pd.DataFrame(events), out / 'events.parquet')
    cfg = json.loads((ROOT / 'configs/simulator.json').read_text())
    manifest = {'scenario': scenario, 'seed': seed, 'count': count, 'sha256': digest, 'config': cfg,
                'origin': 'synthetic', 'sessions': len({e['session_id'] for e in events}),
                'catalog_sha256': hashlib.sha256(json.dumps(records('products'), sort_keys=True).encode()).hexdigest(),
                'note': 'Synthetic sanity check only; not real-user accuracy.'}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    audit('simulator.generated', origin='synthetic', scenario=scenario, seed=seed, count=count, path=str(out))
    if send:
        from pipeline.extract.posthog_client import send_events
        send_events(events)
    else:
        inserted = save_events(events)
        audit('simulator.local_saved', origin='synthetic', count=count, inserted=inserted, duplicates=count-inserted)
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--events', type=int, default=100000)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--scenario', choices=['S1_long_term', 'S2_intent_shift', 'S3_cold_start'], default='S1_long_term')
    p.add_argument('--posthog', action='store_true')
    a = p.parse_args()
    print(json.dumps(generate(a.events, a.seed, a.scenario, a.posthog), indent=2))
