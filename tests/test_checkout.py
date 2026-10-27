from uuid import uuid4
from backend.db import records, get_record


def test_api_filters_and_checkout_idempotency(client):
    p = next(p for p in records("products") if p["stock"])
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/products?limit=0").status_code == 422
    assert client.get("/products/missing").status_code == 404
    payload = {"order_id": str(uuid4()), "user_id": "U0001", "product_ids": [p["id"]]}
    first = client.post("/checkout", json=payload)
    assert first.status_code == 200
    assert client.post("/checkout", json=payload).json() == first.json()
    assert get_record("products", p["id"])["stock"] == p["stock"] - 1
    assert len(records("events")) == 1
    assert client.post("/checkout", json={**payload, "user_id": "U0002"}).status_code == 409


def test_checkout_rolls_back_on_bad_product(client):
    p = next(p for p in records("products") if p["stock"])
    payload = {"order_id": str(uuid4()), "user_id": "U0001", "product_ids": [p["id"], "missing"]}
    assert client.post("/checkout", json=payload).status_code == 404
    assert get_record("products", p["id"])["stock"] == p["stock"]
    assert not records("events")
