import pandas as pd
from datetime import datetime, timezone
from pydantic import ValidationError
from backend.schemas import Event
from backend.settings import pipeline_config
from pipeline.transform.normalize_events import normalize, sessionize

COLUMNS = list(Event.model_fields) + ['ingested_at']


def clean_events(events, users, products, as_of, origin="synthetic"):
    valid, rejected = [], []
    user_ids, product_ids = {u["id"] for u in users}, {p["id"] for p in products}
    for raw in events:
        try:
            raw = {k: None if v is None or (isinstance(v, float) and pd.isna(v)) else v for k, v in raw.items()}
            event = normalize(raw)
            if event.synthetic != (origin == "synthetic"):
                raise ValueError("Origin mismatch")
            if not event.synthetic and (event.bot or event.environment == "dev"):
                raise ValueError("Bot/dev noise excluded from real analytics")
            if (event.synthetic and event.distinct_id not in user_ids) or (event.product_id and event.product_id not in product_ids):
                raise ValueError("Unknown user or product")
            if event.timestamp > as_of:
                raise ValueError("Future timestamp")
            valid.append({**event.model_dump(mode="json"), 'ingested_at': raw.get('ingested_at') or datetime.now(timezone.utc).isoformat()})
        except (ValidationError, ValueError, TypeError) as exc:
            # Pydantic error strings may contain input values; persist only field/error codes.
            reason = ",".join(f"{e['loc']}:{e['type']}" for e in exc.errors()) if isinstance(exc, ValidationError) else str(exc)
            rejected.append({"event_id": str(raw.get("event_id", "")), "reason": reason})
    frame = pd.DataFrame(valid, columns=COLUMNS)
    frame = frame.sort_values(["timestamp", "event_id"]).drop_duplicates("event_id")
    purchases = frame[frame.event_name == "purchase"].drop_duplicates(["distinct_id", "order_id", "order_item_id"])
    frame = pd.concat([frame[frame.event_name != "purchase"], purchases], ignore_index=True)
    frame = sessionize(frame, pipeline_config()["session_gap_minutes"])
    frame["user_id"] = frame.distinct_id
    frame["event_type"] = frame.event_name
    frame["event_ts_utc"] = frame.timestamp
    frame["properties_json"] = frame.apply(lambda r: __import__('json').dumps({k: r[k] for k in ['source', 'environment', 'synthetic']}), axis=1) if not frame.empty else []
    return frame, pd.DataFrame(rejected, columns=["event_id", "reason"])
