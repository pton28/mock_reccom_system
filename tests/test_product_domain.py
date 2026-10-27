import sqlite3
from uuid import uuid4
import pytest
from pydantic import ValidationError
from backend.db import connect, records
from backend.schemas import Product
from backend.catalog import domain_product
from data_generator.generate_products import generate_products
from data_generator.seed import seed


def test_specs_and_validation():
    products = generate_products(30)
    for product in products:
        Product.model_validate(product)
        assert len(product['specifications']) >= 4
        assert 'promotion_id' not in product and 'images' not in product
    laptop = products[0]
    assert {'cpu', 'ram_gb', 'storage_gb'} <= laptop['attributes'].keys()
    with pytest.raises(ValidationError):
        Product.model_validate({**laptop, 'avg_rating': 5.1})
    with pytest.raises(ValidationError):
        Product.model_validate({**laptop, 'stock': -1})


def test_normalized_domain_and_checkout(client):
    product = next(p for p in records('products') if p['stock'] > 0)
    domain = client.get('/catalog/products/' + product['id']).json()
    assert domain['code'] == product['id']
    assert len(domain['specifications']) == len(product['specifications'])
    assert domain['brands'] and domain['categories'] and domain['variants']
    payload = {'order_id': str(uuid4()), 'user_id': 'U0001', 'product_ids': [product['id']]}
    assert client.post('/checkout', json=payload).status_code == 200
    assert client.post('/checkout', json=payload).status_code == 200
    after = domain_product(product['id'])
    assert after['variants'][0]['quantity'] == product['stock'] - 1
    assert after['sold_count'] == 1
    seed(users=20, products=100)
    assert domain_product(product['id'])['variants'][0]['quantity'] == product['stock'] - 1
    with connect() as conn:
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name IN ('promotion','product_image')").fetchall()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute('UPDATE product_variant SET quantity=-1 WHERE id=?', (domain['variants'][0]['id'],))


def test_model_endpoints_and_tables_are_absent(client):
    paths = client.get('/openapi.json').json()['paths']
    assert not any('recommendation' in p or '/models/' in p for p in paths)
    with connect() as conn:
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name IN ('model_registry','recommendation_logs')").fetchall()
