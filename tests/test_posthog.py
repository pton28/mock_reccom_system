import json

import httpx
import pytest

from pipeline.extract import export_posthog, posthog_client
from pipeline.storage import read_bronze


def test_simulator_requires_explicit_test_project(monkeypatch):
    monkeypatch.delenv("POSTHOG_TEST_PROJECT", raising=False)
    with pytest.raises(ValueError, match="dedicated"):
        posthog_client.send_events([])


def test_rate_limit_and_retry(monkeypatch):
    attempts = []
    sleeps = []
    def handler(request):
        attempts.append(request)
        return httpx.Response(429, headers={"Retry-After": "1"}) if len(attempts) == 1 else httpx.Response(200, json={"ok": True})
    monkeypatch.setattr(posthog_client.time, "sleep", sleeps.append)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert posthog_client.request_json(client, "POST", "https://example.test/batch/") == {"ok": True}
    assert len(attempts) == 2 and sleeps == [1]


def test_export_keyset_pagination_checkpoint_and_replay(dataset, monkeypatch):
    for key, value in {"POSTHOG_TEST_PROJECT": "true", "POSTHOG_PROJECT_ID": "123", "POSTHOG_PERSONAL_API_KEY": "test"}.items():
        monkeypatch.setenv(key, value)
    timestamp = "2026-01-05T00:00:00+00:00"
    queries = []
    authorization_headers = []
    pages = [[['00000000-0000-0000-0000-000000000001', timestamp, 'U0001', 'product_view', {'product_id': 'P0001'}]],
             [['00000000-0000-0000-0000-000000000002', timestamp, 'U0001', 'product_view', {'product_id': 'P0002'}]], []]
    def fake_request(client, method, url, **kwargs):
        authorization_headers.append(client.headers.get("Authorization"))
        queries.append(kwargs['json']['query']['query'])
        return {"results": pages.pop(0)}
    monkeypatch.setattr(export_posthog, 'request_json', fake_request)
    assert export_posthog.export_events(page_size=1) == 2
    assert authorization_headers and set(authorization_headers) == {"Bearer test"}
    assert "toString(uuid) > '00000000-0000-0000-0000-000000000001'" in queries[1]
    assert len(read_bronze()) == 2
    checkpoint = json.loads((dataset / 'synthetic/bronze/checkpoint-123.json').read_text())
    assert checkpoint['timestamp'] == timestamp
    assert checkpoint['uuid'].endswith('2')


def test_export_does_not_advance_after_failed_write(dataset, monkeypatch):
    for key, value in {"POSTHOG_TEST_PROJECT": "true", "POSTHOG_PROJECT_ID": "123", "POSTHOG_PERSONAL_API_KEY": "test"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(export_posthog, "request_json", lambda *a, **k: {"results": [["id", "2026-01-05T00:00:00Z", "U0001", "product_view", {}]]})
    def fail(events, origin):
        raise OSError("disk full")
    monkeypatch.setattr(export_posthog, "append_bronze", fail)
    with pytest.raises(OSError):
        export_posthog.export_events()
    assert not (dataset / "synthetic/bronze/checkpoint-123.json").exists()
