import os
import time

import httpx
from backend.observability import audit


def request_json(client, method, url, **kwargs):
    for attempt in range(5):
        try:
            response = client.request(method, url, **kwargs)
            if response.status_code == 429 or response.status_code >= 500:
                audit('posthog.retry', attempt=attempt+1, status_code=response.status_code)
                if attempt == 4:
                    response.raise_for_status()
                delay = response.headers.get("Retry-After", "")
                time.sleep(min(float(delay), 60) if delay.replace(".", "", 1).isdigit() else 2 ** attempt)
                continue
            response.raise_for_status()
            return response.json()
        except httpx.TransportError:
            audit('posthog.transport_retry', attempt=attempt+1)
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("PostHog retries exhausted")


def require_test_project():
    if os.getenv("POSTHOG_TEST_PROJECT", "").lower() != "true":
        raise ValueError("Set POSTHOG_TEST_PROJECT=true only for a dedicated synthetic-data project")


def send_events(events, batch_size=200, interval=0.5):
    require_test_project()
    key = os.environ["POSTHOG_PROJECT_KEY"]
    host = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com").rstrip("/")
    if not key or batch_size < 1:
        raise ValueError("Project key and positive batch size required")
    with httpx.Client(timeout=60) as client:
        for offset in range(0, len(events), batch_size):
            audit('posthog.batch_sending', origin='synthetic', page=offset // batch_size, count=len(events[offset:offset+batch_size]))
            batch = [{"uuid": e["event_id"], "event": e["event_name"], "timestamp": e["timestamp"],
                      "properties": {**e, "synthetic": True, "app": "nutee", "$process_person_profile": False}}
                     for e in events[offset:offset + batch_size]]
            request_json(client, "POST", f"{host}/batch/", json={"api_key": key, "historical_migration": True, "batch": batch})
            audit('posthog.batch_accepted', origin='synthetic', page=offset // batch_size, count=len(batch))
            time.sleep(interval)
