import argparse
import json

from backend.db import connect, init_db
from backend.settings import layer
from backend.catalog import persist_product
from data_generator.generate_users import generate_users
from data_generator.generate_products import generate_products


def seed(users=1000, products=300, seed_value=42):
    init_db()
    datasets = {"users": generate_users(users, seed_value), "products": generate_products(products, seed_value)}
    with connect() as conn:
        for table, rows in datasets.items():
            if table == 'products':
                for row in rows:
                    persist_product(conn, row)
            else:
                conn.executemany(f"INSERT OR IGNORE INTO {table} VALUES (?, ?)", [(r["id"], json.dumps(r)) for r in rows])
            (layer("mock") / f"{table}.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return {k: len(v) for k, v in datasets.items()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=1000)
    parser.add_argument("--products", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    print(seed(args.users, args.products, args.seed))
