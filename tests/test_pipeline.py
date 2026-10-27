from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pandas as pd

from backend.db import records, save_events
from pipeline.run_pipeline import run_pipeline
from pipeline.storage import append_bronze
from pipeline.transform.clean_events import clean_events

NOW = datetime(2026, 2, 1, tzinfo=timezone.utc)


def event(name="product_view", product="P0001", user="U0001", age=0, **extras):
    return {"event_id": str(uuid4()), "timestamp": (NOW - timedelta(days=age)).isoformat(),
            "distinct_id": user, "event_name": name, "product_id": product, "source": "simulator", **extras}


def test_cleaning_deduplicates_purchases_and_quarantines(dataset):
    view = event()
    purchase = event("purchase", order_id="O1")
    data = [view, view, purchase, {**purchase, "event_id": str(uuid4())}, event(user="missing"), event(age=-1)]
    clean, rejected = clean_events(data, records("users"), records("products"), NOW)
    assert len(clean) == 2
    assert len(rejected) == 2


def test_aggregates_preserve_counts_without_scoring(dataset):
    save_events([event('product_impression'), event('product_view'), event('product_view')])
    result = run_pipeline(as_of=NOW)
    counts = pd.read_parquet(dataset/'synthetic/gold'/result['generation']/'user_item_event_counts.parquet')
    assert counts.set_index('event_name').event_count.to_dict() == {'product_impression': 1, 'product_view': 2}
    assert not {'score', 'strength', 'confidence'} & set(counts.columns)


def test_pipeline_rerun_is_idempotent(dataset):
    save_events([event(), event("search", product=None, query="laptop")])
    first = run_pipeline(as_of=NOW)
    before = pd.read_parquet(dataset / "synthetic/gold" / first["generation"] / "user_item_event_counts.parquet")
    second = run_pipeline(as_of=NOW)
    after = pd.read_parquet(dataset / "synthetic/gold" / second["generation"] / "user_item_event_counts.parquet")
    pd.testing.assert_frame_equal(before, after)
    assert first["events"] == second["events"] == 2
    assert len(list((dataset / "synthetic/bronze").glob("*.parquet"))) == 1


def test_empty_pipeline_and_imported_duplicate(dataset):
    assert run_pipeline(as_of=NOW)["users"] == 0
    e = event()
    append_bronze([e, e])
    assert run_pipeline(source="bronze", as_of=NOW)["events"] == 1
