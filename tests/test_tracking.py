import json
from datetime import datetime, timezone
from uuid import uuid4

import jsonschema
import pytest
from pydantic import ValidationError

from backend.db import records
from backend.schemas import Event
from backend.settings import ROOT
from data_generator.simulate_sessions import simulate_sessions as simulate


def test_simulation_is_seeded_and_schema_valid(dataset):
    users, products = records("users"), records("products")
    first = list(simulate(users, products, 200, seed=15))
    assert first == list(simulate(users, products, 200, seed=15))
    assert first != list(simulate(users, products, 200, seed=16))
    assert len({e["event_id"] for e in first}) == 200
    schema = json.loads((ROOT / "configs/event_schema.json").read_text())
    for event in first:
        Event.model_validate(event)
        jsonschema.validate(event, schema, format_checker=jsonschema.FormatChecker())


def test_invalid_events_rejected():
    base = dict(event_id=uuid4(), distinct_id="U0001", timestamp=datetime.now(timezone.utc))
    for data in [{"event_name": "product_view"}, {"event_name": "search", "query": " "},
                 {"event_name": "purchase", "product_id": "P0001"}, {"event_name": "unknown"}]:
        with pytest.raises(ValidationError):
            Event(**base, **data)


def test_event_endpoint_deduplicates(client):
    event = dict(event_id=str(uuid4()), timestamp=datetime.now(timezone.utc).isoformat(),
                 distinct_id="U0001", event_name="product_view", product_id="P0001")
    assert client.post("/events", json=event).json()["duplicate"] is False
    assert client.post("/events", json=event).json()["duplicate"] is True
    event["distinct_id"] = "missing"
    assert client.post("/events", json=event).status_code == 404
    event["distinct_id"] = "U0001"
    event["event_name"] = "purchase"
    event["order_id"] = "test"
    assert client.post("/events", json=event).status_code == 422


def test_product_context_and_normalization():
    from pipeline.transform.normalize_events import normalize
    base = dict(event_id=str(uuid4()), timestamp=datetime.now(timezone.utc).isoformat(),
                distinct_id="U0001", product_id="P0001", event_name="product_click",
                page="home", list_id="home-list", position=3)
    schema = json.loads((ROOT / "configs/event_schema.json").read_text())
    jsonschema.validate(base, schema)
    assert Event(**base).position == 3
    for field, value in [("position", 0), ("page", "invalid_page"),
                         ("event_name", "invalid_event")]:
        invalid = {**base, field: value}
        with pytest.raises(ValidationError):
            Event(**invalid)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema)
    assert normalize({'properties': base}).model_dump()['list_id'] == 'home-list'
    with pytest.raises(ValidationError):
        normalize({**base, 'position': 0})
