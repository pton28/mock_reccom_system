"""Seed products and export synthetic history. No AI training or evaluation."""
import argparse
import json
from backend.db import records
from backend.schemas import Event
from backend.settings import layer
from data_generator.simulate_sessions import generate
from pipeline.run_pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--events', type=int, default=100000)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    generated = generate(args.events, args.seed)
    pipeline = run_pipeline()
    from collections import Counter
    events = records('events')
    for event in events:
        Event.model_validate(event)
    summary = {'users': len(records('users')), 'products': len(records('products')),
               'events': len(events), 'event_counts': dict(Counter(e['event_name'] for e in events)),
               'sessions': len({e['session_id'] for e in events}), 'seed': args.seed,
               'sha256': generated['sha256'], 'rejected': pipeline['rejected'], 'scope': 'product_and_tracking_only',
               'note': 'Synthetic behavioral history, not real orders or inventory movements.'}
    (layer('raw', 'synthetic') / 'demo-summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
