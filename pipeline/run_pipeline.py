import argparse
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from backend.db import init_db, records
from backend.settings import layer
from backend.observability import audit
from pipeline.storage import append_bronze, read_bronze, write_parquet
from pipeline.transform.clean_events import clean_events


def run_pipeline(source="local", as_of=None, origin="synthetic"):
    init_db()
    run_id = uuid4().hex
    audit("pipeline.started", run_id=run_id, origin=origin, source=source)
    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        raise ValueError("as_of must include timezone")
    if source == "local":
        # Snapshot is deduplicated against previous Bronze batches before appending.
        from pipeline.transform.normalize_events import normalize
        known = set()
        for raw in read_bronze(origin):
            try:
                known.add(str(normalize(raw).event_id))
            except ValueError:
                pass
        append_bronze([e for e in records("events") if e["event_id"] not in known and e.get("synthetic", True) == (origin == "synthetic")], origin)
    elif source != "bronze":
        raise ValueError("source must be local or bronze")
    products, users = records("products"), records("users")
    raw = read_bronze(origin)
    events, rejected = clean_events(raw, users, products, as_of, origin)
    write_parquet(events, layer("silver", origin) / "events.parquet")
    write_parquet(rejected, layer("silver", origin) / "rejected.parquet")
    audit("silver.validated", run_id=run_id, origin=origin, count=len(events), rejected=len(rejected), duplicates=len(raw)-len(events)-len(rejected))
    for row in rejected.itertuples():
        audit("silver.rejected", run_id=run_id, origin=origin, event_id=row.event_id, reason=row.reason)
    # Neutral data summaries: counts and sequences, no model scores or labels.
    import pandas as pd
    product_events = events[events.product_id.notna()]
    counts = product_events.groupby(['distinct_id', 'product_id', 'event_name'], as_index=False).agg(
        event_count=('event_id', 'size'), first_timestamp=('timestamp', 'min'), last_timestamp=('timestamp', 'max'))
    counts = counts.rename(columns={'distinct_id': 'user_id'})
    sequences = []
    for (user, sid), group in events.sort_values(['timestamp', 'event_id']).groupby(['distinct_id', 'session_id']):
        sequences.append({'user_id': user, 'session_id': sid, 'item_ids': group.product_id.tolist(),
                          'event_types': group.event_name.tolist(), 'timestamps': group.timestamp.tolist()})
    tables = {'user_item_event_counts': counts,
              'session_sequences': pd.DataFrame(sequences, columns=['user_id', 'session_id', 'item_ids', 'event_types', 'timestamps'])}
    # Publish one pointer after all Gold tables are written; API readers get one complete generation.
    generation = uuid4().hex
    output = layer("gold", origin) / generation
    output.mkdir()
    for name, frame in tables.items():
        write_parquet(frame, output / f"{name}.parquet")
    manifest = {"generation": generation, "run_id": run_id, "origin": origin, "as_of": as_of.isoformat(), "events": len(events),
                "rejected": len(rejected), "users": int(events.distinct_id.nunique()),
                "tables": {name: len(frame) for name, frame in tables.items()}}
    temp = layer("gold", origin) / f"manifest-{generation}.tmp"
    temp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    os.replace(temp, layer("gold", origin) / "manifest.json")
    audit("gold.published", run_id=run_id, origin=origin, count=len(counts), cutoff=manifest['as_of'], path=str(output))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["local", "bronze"], default="local")
    parser.add_argument("--origin", choices=["synthetic", "real"], default="synthetic")
    parser.add_argument("--as-of", help="Timezone-aware ISO timestamp; omitted means current UTC")
    args = parser.parse_args()
    print(json.dumps(run_pipeline(args.source, datetime.fromisoformat(args.as_of) if args.as_of else None, args.origin), indent=2))
