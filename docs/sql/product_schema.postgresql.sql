-- PostgreSQL product domain; no image or promotion entities.
CREATE TABLE IF NOT EXISTS product (
 id SERIAL PRIMARY KEY, code VARCHAR(100) NOT NULL UNIQUE,
 name VARCHAR(255) NOT NULL, description TEXT,
 avg_rating NUMERIC(2,1) CHECK(avg_rating BETWEEN 0 AND 5),
 sold_count INTEGER NOT NULL DEFAULT 0 CHECK(sold_count >= 0),
 is_published BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS brand (
 id SERIAL PRIMARY KEY, name VARCHAR(255) NOT NULL UNIQUE,
 created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS category (
 id SERIAL PRIMARY KEY, parent INTEGER REFERENCES category(id),
 name VARCHAR(255) NOT NULL UNIQUE, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
 CHECK(parent IS NULL OR parent <> id)
);
CREATE TABLE IF NOT EXISTS product_variant (
 id SERIAL PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES product(id),
 sku VARCHAR(16) NOT NULL UNIQUE CHECK(length(sku) <= 16),
 price INTEGER NOT NULL CHECK(price >= 0), quantity INTEGER NOT NULL CHECK(quantity >= 0),
 created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS product_specification (
 id SERIAL PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES product(id),
 specification_name VARCHAR(255) NOT NULL, specification_value TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
 UNIQUE(product_id, specification_name)
);
CREATE TABLE IF NOT EXISTS product_brand (
 product_id INTEGER NOT NULL REFERENCES product(id), brand_id INTEGER NOT NULL REFERENCES brand(id),
 PRIMARY KEY(product_id, brand_id)
);
CREATE TABLE IF NOT EXISTS product_category (
 product_id INTEGER NOT NULL REFERENCES product(id), cat_id INTEGER NOT NULL REFERENCES category(id),
 PRIMARY KEY(product_id, cat_id)
);
CREATE INDEX IF NOT EXISTS variant_product ON product_variant(product_id);
CREATE INDEX IF NOT EXISTS brand_products ON product_brand(brand_id);
CREATE INDEX IF NOT EXISTS category_products ON product_category(cat_id);
