import os
from uuid import uuid4
import pandas as pd
import json
from datetime import datetime, timezone
from backend.settings import layer
from backend.observability import audit


def write_parquet(frame, path):
    temp = path.with_suffix(f".{uuid4().hex}.tmp")
    try:
        frame.to_parquet(temp, index=False)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def append_bronze(events, origin="synthetic"):
    if events:
        path = layer("bronze", origin) / f"events-{uuid4().hex}.parquet"
        rows = [{"raw_json": json.dumps(e, default=str), "ingested_at": datetime.now(timezone.utc).isoformat()} for e in events]
        write_parquet(pd.DataFrame(rows), path)
        audit("bronze.written", origin=origin, count=len(rows), path=str(path))


def read_bronze(origin="synthetic"):
    files = sorted(layer("bronze", origin).glob("*.parquet"))
    if origin == "synthetic":
        files += sorted(layer("bronze").glob("*.parquet"))  # read-only legacy migration
    events = []
    for file in files:
        frame = pd.read_parquet(file)
        if 'raw_json' in frame:
            for row in frame.itertuples():
                event = json.loads(row.raw_json)
                event.setdefault('ingested_at', row.ingested_at)
                events.append(event)
        else:
            events.extend(frame.to_dict('records'))
    return events
