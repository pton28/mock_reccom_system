"""Normalized product domain and the existing storefront JSON projection."""
import json
from datetime import datetime, timezone
from backend.db import connect
from backend.schemas import Product


def persist_product(conn, raw):
    product = Product.model_validate(raw)
    now = datetime.now(timezone.utc).isoformat()
    existing = conn.execute('SELECT id FROM product WHERE code=?', (product.id,)).fetchone()
    if existing:
        return existing[0]  # Re-seeding must not reset stock or orders.
    pid = conn.execute('INSERT INTO product(code,name,description,avg_rating,sold_count,is_published,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
        (product.id, product.name, product.description, product.avg_rating, product.sold_count, product.is_published, now, now)).lastrowid
    for table, label, junction, column in [('brand', product.brand, 'product_brand', 'brand_id'), ('category', product.category, 'product_category', 'cat_id')]:
        conn.execute(f'INSERT OR IGNORE INTO {table}(name,created_at,updated_at) VALUES (?,?,?)', (label, now, now))
        identity = conn.execute(f'SELECT id FROM {table} WHERE name=?', (label,)).fetchone()[0]
        conn.execute(f'INSERT INTO {junction}(product_id,{column}) VALUES (?,?)', (pid, identity))
    for variant in product.variants:
        conn.execute('INSERT INTO product_variant(product_id,sku,price,quantity,created_at,updated_at) VALUES (?,?,?,?,?,?)',
                     (pid, variant.sku, variant.price, variant.quantity, now, now))
    for spec in product.specifications:
        conn.execute('INSERT INTO product_specification(product_id,specification_name,specification_value,created_at,updated_at) VALUES (?,?,?,?,?)',
                     (pid, spec.specification_name, spec.specification_value, now, now))
    projection = product.model_dump(mode='json')
    projection['domain_id'] = pid
    conn.execute('INSERT INTO products(id,payload) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                 (product.id, json.dumps(projection)))
    return pid


def domain_product(code):
    with connect() as conn:
        row = conn.execute('SELECT * FROM product WHERE code=?', (code,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        for key, table in [('variants', 'product_variant'), ('specifications', 'product_specification')]:
            result[key] = [dict(r) for r in conn.execute(f'SELECT * FROM {table} WHERE product_id=? ORDER BY id', (row['id'],))]
        result['brands'] = [dict(r) for r in conn.execute('SELECT b.* FROM brand b JOIN product_brand j ON j.brand_id=b.id WHERE j.product_id=?', (row['id'],))]
        result['categories'] = [dict(r) for r in conn.execute('SELECT c.* FROM category c JOIN product_category j ON j.cat_id=c.id WHERE j.product_id=?', (row['id'],))]
        return result
