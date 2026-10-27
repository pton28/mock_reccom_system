import json
import os
from datetime import timedelta
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from threading import Lock
from uuid import NAMESPACE_URL, uuid5

from fastapi import FastAPI, HTTPException, Query, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.db import connect, get_record, init_db, records, save_events
from backend.schemas import Checkout, Event, Product
from pipeline.run_pipeline import run_pipeline
from backend.observability import audit
from backend.settings import layer
from uuid import uuid4
import secrets
import time

pipeline_lock = Lock()


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title="NUTEE Product and Tracking Demo",
              version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:8080").split(","),
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


@app.middleware('http')
async def trace_request(request: Request, call_next):
    request_id = str(uuid4())
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as error:
        audit('api.failed', request_id=request_id, reason=type(error).__name__)
        raise
    response.headers['X-Request-ID'] = request_id
    audit('api.completed', request_id=request_id, status_code=response.status_code,
          duration_ms=round((time.perf_counter()-start)*1000, 2))
    return response


def internal_access(x_internal_token: str | None = Header(None)):
    if os.getenv('APP_ENV', 'dev') == 'dev':
        return
    expected = os.getenv('INTERNAL_API_TOKEN', '')
    if not expected or not x_internal_token or not secrets.compare_digest(expected, x_internal_token):
        raise HTTPException(403, 'Internal endpoint requires authorization')


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/users")
def users(limit: int = Query(100, ge=1, le=1000)):
    # Hide persona fields even when reading a database from an older release.
    return [{"id": u["id"], "name": f"User {u['id']}"} for u in records("users")[:limit]]


@app.get("/products")
def products(q: str = "", category: str | None = None, offset: int = Query(0, ge=0), limit: int = Query(24, ge=1, le=300)):
    catalog = records("products")
    selected = [p for p in catalog if (not category or p["category_id"] == category)
                and q.lower() in (p["name"] + " " + p["category"] + " " + p["brand"]).lower()]
    return {"items": selected[offset:offset + limit], "total": len(selected),
            "categories": sorted({p["category_id"] for p in catalog})}


@app.get("/products/{product_id}", response_model=Product)
def product(product_id: str):
    result = get_record("products", product_id)
    if not result:
        raise HTTPException(404, "Product not found")
    return result


@app.get("/catalog/products/{product_code}")
def catalog_product(product_code: str):
    from backend.catalog import domain_product
    result = domain_product(product_code)
    if result is None:
        raise HTTPException(404, "Product not found")
    return result



@app.post("/events", status_code=201)
def capture(event: Event):
    if os.getenv('APP_ENV', 'dev') == 'production' and event.synthetic:
        raise HTTPException(
            403, 'Synthetic events require the demo deployment')
    if event.synthetic and not get_record("users", event.distinct_id):
        raise HTTPException(404, "Unknown user")
    if event.product_id and not get_record("products", event.product_id):
        raise HTTPException(404, "Unknown product")
    if event.timestamp > (datetime.now(timezone.utc) + timedelta(seconds=5)):
        raise HTTPException(422, "Future timestamps are not accepted")
    if event.event_name == "purchase":
        raise HTTPException(422, "Complete a purchase through /checkout")
    inserted = save_events([event.model_dump(mode="json")])
    audit('event.local_saved', event_id=event.event_id, event_name=event.event_name, user_id=event.distinct_id,
          product_id=event.product_id, session_id=event.session_id, origin='synthetic' if event.synthetic else 'real',
          source=event.source, inserted=inserted, duplicates=1-inserted)
    return {"accepted": True, "duplicate": inserted == 0}


@app.post("/checkout")
def checkout(request: Checkout):
    if len(request.product_ids) != len(set(request.product_ids)):
        raise HTTPException(
            422, "One unit per product is supported in this demo")
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT payload FROM orders WHERE order_id=?", (str(request.order_id),)).fetchone()
        if existing:
            order = json.loads(existing[0])
            if order["user_id"] != request.user_id or sorted(order["product_ids"]) != sorted(request.product_ids):
                raise HTTPException(
                    409, "Order ID was already used with a different cart")
            return order
        if not conn.execute("SELECT 1 FROM users WHERE id=?", (request.user_id,)).fetchone():
            raise HTTPException(404, "Unknown user")
        total, events = 0, []
        timestamp = datetime.now(timezone.utc).isoformat()
        for pid in request.product_ids:
            row = conn.execute(
                "SELECT payload FROM products WHERE id=?", (pid,)).fetchone()
            if not row:
                raise HTTPException(404, f"Unknown product {pid}")
            item = json.loads(row[0])
            if item["stock"] < 1:
                raise HTTPException(409, f"{item['name']} is out of stock")
            item["stock"] -= 1
            item['variants'][0]['quantity'] = item['stock']
            item['sold_count'] = item.get('sold_count', 0) + 1
            changed = conn.execute('UPDATE product_variant SET quantity=quantity-1,updated_at=? WHERE sku=? AND quantity>0',
                (timestamp, item['variants'][0]['sku'])).rowcount
            if changed != 1:
                raise HTTPException(409, 'SKU stock is unavailable')
            conn.execute('UPDATE product SET sold_count=sold_count+1,updated_at=? WHERE code=?', (timestamp, pid))
            total += item["price"]
            conn.execute("UPDATE products SET payload=? WHERE id=?",
                         (json.dumps(item), pid))
            events.append(Event(event_id=uuid5(NAMESPACE_URL, f"{request.order_id}:{pid}"), timestamp=timestamp,
                                distinct_id=request.user_id, event_name="purchase", product_id=pid,
                                order_id=str(request.order_id), order_item_id=f'{request.order_id}:{pid}',
                                session_id=request.session_id, page="cart").model_dump(mode="json"))
        conn.executemany("INSERT OR IGNORE INTO events VALUES (?, ?)", [
                         (e["event_id"], json.dumps(e)) for e in events])
        order = {"order_id": str(request.order_id), "user_id": request.user_id, "product_ids": request.product_ids,
                 "total": total, "events": events, "status": "completed"}
        conn.execute("INSERT INTO orders VALUES (?, ?, ?)", (str(
            request.order_id), request.user_id, json.dumps(order)))
    for event in events:
        audit('purchase.committed', event_id=event['event_id'], user_id=request.user_id,
              product_id=event['product_id'], session_id=request.session_id, origin='synthetic')
    return order


@app.get("/analytics/status", dependencies=[Depends(internal_access)])
def status(origin: str = Query('synthetic', pattern='^(synthetic|real)$')):
    path = layer('gold', origin) / 'manifest.json'
    manifest = json.loads(path.read_text()) if path.exists() else {}
    with connect() as conn:
        counts = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[
            0] for table in ["users", "products", "events", "orders"]}
        counts['events'] = sum(e.get('synthetic', True) == (
            origin == 'synthetic') for e in records('events'))
        counts['posthog_imported'] = conn.execute(
            'SELECT COUNT(*) FROM posthog_events WHERE origin=?', (origin,)).fetchone()[0]
    return {**counts, 'origin': origin, "pipeline": manifest}


@app.post("/pipeline/run", dependencies=[Depends(internal_access)])
@app.post("/internal/pipeline/run", dependencies=[Depends(internal_access)])
def rebuild(origin: str = Query('synthetic', pattern='^(synthetic|real)$'), source: str = Query('local', pattern='^(local|bronze)$')):
    if not pipeline_lock.acquire(blocking=False):
        raise HTTPException(409, "Pipeline is already running")
    try:
        return run_pipeline(source=source, origin=origin)
    finally:
        pipeline_lock.release()


@app.get('/internal/events', dependencies=[Depends(internal_access)])
def inspect_events(origin: str = Query('synthetic', pattern='^(synthetic|real)$'), event_id: str | None = None,
                   limit: int = Query(30, ge=1, le=200)):
    from pipeline.transform.normalize_events import normalize
    with connect() as conn:
        sql = 'SELECT payload FROM posthog_events WHERE origin=?'
        args = [origin]
        if event_id:
            sql += ' AND event_id=?'
            args.append(event_id)
        sql += ' ORDER BY rowid DESC LIMIT ?'
        args.append(limit)
        exported = [json.loads(r[0]) for r in conn.execute(sql, args)]
    local = [e for e in records('events') if e.get('synthetic', True) == (
        origin == 'synthetic') and (not event_id or e['event_id'] == event_id)][-limit:]

    def safe(raw):
        try:
            e = normalize(raw).model_dump(mode='json')
            return {k: v for k, v in e.items() if k != 'query'}
        except ValueError:
            return {'event_id': raw.get('event_id'), 'status': 'invalid_see_silver_rejected'}
    return {'origin': origin, 'local': [safe(e) for e in reversed(local)], 'posthog_imported': [safe(e) for e in exported]}


@app.get('/internal/metrics', dependencies=[Depends(internal_access)])
def observed_metrics(origin: str = Query('synthetic', pattern='^(synthetic|real)$')):
    from collections import Counter
    from pipeline.transform.normalize_events import normalize
    with connect() as conn:
        imported = [json.loads(r[0]) for r in conn.execute(
            'SELECT payload FROM posthog_events WHERE origin=?', (origin,))]
    by_id = {}
    for raw in records('events') + imported:
        try:
            event = normalize(raw)
            if event.synthetic == (origin == 'synthetic') and not event.bot:
                by_id[str(event.event_id)] = event
        except ValueError:
            continue
    events = list(by_id.values())
    counts = Counter(e.event_name for e in events)
    exposures = {(e.distinct_id, e.list_id, e.product_id)
                 for e in events if e.event_name == 'product_impression' and e.list_id}
    clicks = {(e.distinct_id, e.list_id, e.product_id)
              for e in events if e.event_name == 'product_click' and e.list_id}
    return {'origin': origin, 'claim': 'synthetic_observations' if origin == 'synthetic' else 'observed_real',
            'event_counts': dict(counts), 'unique_exposure_pairs': len(exposures), 'matched_click_pairs': len(clicks & exposures),
            'product_list_ctr': len(clicks & exposures)/len(exposures) if exposures else None,
            'purchase_actions': len({(e.distinct_id, e.order_id, e.order_item_id) for e in events if e.event_name == 'purchase'}),
            'attribution': 'CTR joins unique user/list/item pairs; events without list_id excluded; no causal conversion attribution inferred'}
