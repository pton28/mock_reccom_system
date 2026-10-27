from datetime import timedelta
from uuid import uuid4
import pytest
from backend.db import records, save_events
from backend.schemas import Event
from backend.observability import audit
from pipeline.storage import append_bronze, read_bronze
from pipeline.transform.normalize_events import normalize
from pipeline.transform.clean_events import clean_events
from pipeline.run_pipeline import run_pipeline
from data_generator.simulate_sessions import simulate_sessions
from tests.test_pipeline import event, NOW

def test_nested_posthog_contract_and_real_consent():
    raw = event()
    raw.update(session_id='s', synthetic=False, environment='production', consent=True, source='website')
    normalized = normalize({'uuid': raw['event_id'], 'event': 'product_view', 'timestamp': raw['timestamp'],
                            'distinct_id': raw['distinct_id'], 'properties': raw})
    assert not normalized.synthetic and normalized.session_id == 's'
    with pytest.raises(ValueError, match='consent'):
        Event.model_validate({**raw, 'consent':False})
    with pytest.raises(ValueError, match='simulator'):
        Event.model_validate({**raw, 'source':'simulator'})
    with pytest.raises(ValueError, match='order_item_id'):
        Event.model_validate({**raw, 'event_name':'purchase', 'order_id':'order'})

def test_session_gap_origin_and_business_dedupe(dataset):
    a=event(); b={**event(), 'timestamp':(NOW-timedelta(minutes=10)).isoformat()}
    c={**event(), 'timestamp':(NOW-timedelta(minutes=50)).isoformat()}
    frame,_=clean_events([a,b,c],records('users'),records('products'),NOW)
    assert frame.session_id.nunique()==2
    real={**a,'event_id':str(uuid4()),'synthetic':False,'consent':True,'source':'website','environment':'production'}
    append_bronze([a]); append_bronze([real],'real')
    assert len(read_bronze('synthetic'))==len(read_bronze('real'))==1
    assert run_pipeline('bronze',NOW,'real')['events']==1
    assert run_pipeline('bronze',NOW,'synthetic')['events']==1

@pytest.mark.parametrize('scenario',['S1_long_term','S2_intent_shift','S3_cold_start'])
def test_seeded_exposure_funnel(dataset,scenario):
    users,products=records('users'),records('products')
    events=list(simulate_sessions(users,products,1000,42,scenario))
    assert events==list(simulate_sessions(users,products,1000,42,scenario))
    seen={}
    for e in events:
        Event.model_validate(e)
        key=(e['session_id'],e['product_id'])
        history=seen.setdefault(key,[])
        if e['event_name']=='product_click': assert 'product_impression' in history
        if e['event_name']=='product_view': assert 'product_click' in history
        if e['event_name']=='purchase': assert 'add_to_cart' in history and e['order_item_id']
        history.append(e['event_name'])
        assert not any(key in e for key in ['persona','budget','hidden_preferences'])

def test_audit_does_not_log_sensitive_fields(dataset):
    audit('test',event_id='safe',api_key='secret',query='private text',email='secret@email.test')
    logged=(dataset/'logs/audit.jsonl').read_text()
    assert 'safe' in logged and 'secret' not in logged and 'private text' not in logged

def test_mixed_timestamp_precision(dataset):
    save_events([event(), {**event(), 'timestamp': '2026-01-31T23:59:59.123456+00:00'}])
    result=run_pipeline(as_of=NOW)
    assert result['events']==2 and result['users']==1

def test_simulator_ids_are_scoped_to_dataset(dataset):
    users,products=records('users'),records('products')
    a=list(simulate_sessions(users,products,100))
    b=list(simulate_sessions(users,products,200))
    assert {e['event_id'] for e in a}.isdisjoint(e['event_id'] for e in b)


def test_internal_auth(client, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('INTERNAL_API_TOKEN', 'private-test')
    assert client.post('/pipeline/run').status_code == 403
    assert client.get('/analytics/status').status_code == 403
    assert client.get('/analytics/status', headers={'X-Internal-Token': 'private-test'}).status_code == 200


def test_product_list_metrics(client):
    base = {**event('product_impression'), 'session_id': 's', 'list_id': 'l', 'position': 1}
    save_events([base, {**base, 'event_id': str(uuid4()), 'event_name': 'product_click'}])
    assert client.get('/internal/metrics').json()['product_list_ctr'] == 1
    assert client.get('/internal/metrics?origin=real').json()['product_list_ctr'] is None
