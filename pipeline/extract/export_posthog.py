"""HogQL keyset export. Checkpoints commit only after durable Bronze writes."""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone

import httpx

from backend.settings import layer
from pipeline.extract.posthog_client import request_json, require_test_project
from pipeline.storage import append_bronze
from backend.db import save_exported
from backend.observability import audit
from pipeline.transform.normalize_events import normalize


def sql_string(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def export_events(page_size=1000, lookback_hours=48, since=None, origin="synthetic"):
    if origin not in {'real', 'synthetic'}:
        raise ValueError('Invalid origin')
    if origin == 'synthetic':
        require_test_project()
    if not 1 <= page_size <= 10000 or lookback_hours < 0:
        raise ValueError("Invalid export window or page size")
    prefix = 'POSTHOG_REAL_' if origin == 'real' else 'POSTHOG_'
    host = os.getenv(prefix + "API_HOST", "https://us.posthog.com").rstrip("/")
    project = os.environ[prefix + "PROJECT_ID"]
    token = os.environ[prefix + "PERSONAL_API_KEY"]
    if origin == 'real' and project == os.getenv('POSTHOG_PROJECT_ID'):
        raise ValueError('Real and synthetic must use separate PostHog projects')
    checkpoint = layer("bronze", origin) / f"checkpoint-{project}.json"
    previous = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
    previous_time = datetime.fromisoformat(previous.get("timestamp", "1970-01-01T00:00:00+00:00"))
    start = datetime.fromisoformat(since) if since else previous_time - timedelta(hours=lookback_hours)
    if start.tzinfo is None:
        raise ValueError("--since needs a timezone")
    cursor_time, cursor_id = start.isoformat(), ""
    upper = datetime.now(timezone.utc).isoformat()
    total = 0
    audit('posthog.export_started', origin=origin, cutoff=upper, checkpoint=cursor_time)
    with httpx.Client(timeout=120, headers={"Authorization": f"Bearer {token}"}) as client:
        while True:
            query = f"""SELECT uuid, timestamp, distinct_id, event, properties FROM events
                WHERE properties.app = 'nutee' AND properties.synthetic = {'true' if origin == 'synthetic' else 'false'}
                AND timestamp <= toDateTime64({sql_string(upper)}, 6)
                AND (timestamp > toDateTime64({sql_string(cursor_time)}, 6)
                  OR (timestamp = toDateTime64({sql_string(cursor_time)}, 6) AND toString(uuid) > {sql_string(cursor_id)}))
                ORDER BY timestamp, toString(uuid) LIMIT {int(page_size)}"""
            result = request_json(client, "POST", f"{host}/api/projects/{project}/query/",
                                  json={"query": {"kind": "HogQLQuery", "query": query}})
            rows = result.get("results")
            if not isinstance(rows, list):
                raise RuntimeError("PostHog query did not return synchronous results")
            if not rows:
                break
            events = []
            for uid, timestamp, distinct_id, name, props in rows:
                props = json.loads(props) if isinstance(props, str) else props
                events.append({'uuid': uid, 'event_id': props.get('event_id') or props.get('$insert_id') or uid,
                               'timestamp': timestamp, 'distinct_id': distinct_id, 'event': name, 'properties': props})
            append_bronze(events, origin)
            inserted = save_exported(events, origin)
            audit('posthog.export_page_saved', origin=origin, count=len(events), inserted=inserted, duplicates=len(events)-inserted)
            for raw in events:
                audit('posthog.event_imported', origin=origin, event_id=raw['event_id'], event_name=raw['event'], user_id=raw['distinct_id'])
            cursor_id, cursor_time = str(rows[-1][0]), str(rows[-1][1])
            parsed = datetime.fromisoformat(cursor_time.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            cursor_time = parsed.isoformat()
            if parsed >= previous_time:
                tmp = checkpoint.with_suffix(".tmp")
                tmp.write_text(json.dumps({"timestamp": cursor_time, "uuid": cursor_id}), encoding="utf-8")
                os.replace(tmp, checkpoint)
                previous_time = parsed
                audit('posthog.checkpoint_committed', origin=origin, checkpoint=cursor_time)
            total += len(rows)
            if len(rows) < page_size:
                break
    audit('posthog.export_completed', origin=origin, count=total)
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--lookback-hours", type=int, default=48)
    parser.add_argument("--since", help="ISO timestamp; use to backfill events older than the lookback window")
    parser.add_argument('--origin', choices=['synthetic', 'real'], default='synthetic')
    args = parser.parse_args()
    print({"exported": export_events(args.page_size, args.lookback_hours, args.since, args.origin)})
