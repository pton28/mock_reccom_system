import json

from backend.db import connect, records
from data_generator.generate_products import generate_products
from data_generator.generate_users import generate_users
from data_generator.simulate_sessions import simulate_sessions
from pipeline.run_pipeline import run_pipeline


def test_generated_data_has_no_assigned_labels():
    users, products = generate_users(10), generate_products(30)
    assert all(set(user) == {'id', 'name'} for user in users)
    assert all('tags' not in product for product in products)
    text = json.dumps(products).lower()
    assert not any(label in text for label in ['gaming', 'performance', 'office', 'productivity', 'premium'])


def test_simulator_ignores_user_personas_and_demographics():
    users, products = generate_users(10), generate_products(30)
    altered = [{**u, 'name': 'Changed', 'persona': 'professional', 'occupation': 'engineer',
                'preferred_brand': 'B01', 'budget_usd': [1, 2], 'novelty_preference': 100} for u in users]
    assert list(simulate_sessions(users, products, 400)) == list(simulate_sessions(altered, products, 400))


def test_empty_experiment_and_safe_user_api(client):
    assert not records('events')
    run_pipeline()
    with connect() as conn:
        conn.execute('UPDATE users SET payload=? WHERE id=?',
                     (json.dumps({'id': 'U0001', 'name': 'Old name', 'persona': 'professional'}), 'U0001'))
    users = client.get('/users').json()
    assert all(set(user) == {'id', 'name'} for user in users)
    products = client.get('/products').json()['items']
    assert products and all('tags' not in p for p in products)
    assert client.get('/products?q=gaming').json()['total'] == 0
