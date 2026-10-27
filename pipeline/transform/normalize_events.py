import json
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from backend.schemas import Event


def normalize(raw):
    props = raw.get("properties", {})
    props = json.loads(props) if isinstance(props, str) else props
    props = props or {}
    merged = {**props, **{k: v for k, v in raw.items() if k != "properties" and v is not None}}
    if raw.get('event'):
        merged['event_name'] = raw['event']
    aliases = {"event_name": ["event", "event_type"], "timestamp": ["event_ts_utc"],
               "distinct_id": ["user_id", "anonymous_id"], "query": ["search_query"]}
    for field, options in aliases.items():
        if merged.get(field) is None:
            merged[field] = next((merged[k] for k in options if merged.get(k) is not None), None)
    merged["event_id"] = merged.get("event_id") or merged.get("$insert_id") or merged.get("uuid")
    # Missing legacy origin is synthetic only, never silently accepted as real.
    merged.setdefault("synthetic", True)
    merged.setdefault("environment", "dev")
    merged.setdefault("source", "website")
    return Event.model_validate({k: v for k, v in merged.items() if k in Event.model_fields and v is not None})


def sessionize(frame, gap_minutes=30):
    if frame.empty:
        return frame
    frame = frame.sort_values(["distinct_id", "timestamp", "event_id"]).copy()
    for user, group in frame.groupby("distinct_id", sort=False):
        previous, session = None, None
        for idx, row in group.iterrows():
            ts = datetime.fromisoformat(row.timestamp.replace("Z", "+00:00"))
            explicit = row.session_id
            if explicit:
                session = explicit
            elif previous is None or (ts - previous).total_seconds() > gap_minutes * 60:
                session = str(uuid5(NAMESPACE_URL, f"nutee-session:{user}:{row.event_id}"))
            frame.at[idx, "session_id"] = session
            previous = ts
    return frame
