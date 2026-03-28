"""
db/setup_product_replicas.py

Creates the five product_db replicas (product_db_0 … product_db_4) required
for PA3 Raft replication.

Each replica gets the same schema as the original product_db:
    - items, item_keywords, cart, purchases, categories

Reads MySQL credentials from .env (PRODUCT_DB_HOST/PORT/USER/PASSWORD).

Usage:
    cd <project root>
    python db/setup_product_replicas.py

Options:
    --drop    Drop and recreate each database if it already exists.
    --no-seed Skip inserting stub seed rows.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import os
import mysql.connector

HOST     = os.getenv("PRODUCT_DB_HOST", "localhost")
PORT     = int(os.getenv("PRODUCT_DB_PORT", "3306"))
USER     = os.getenv("PRODUCT_DB_USER", "root")
PASSWORD = os.getenv("PRODUCT_DB_PASSWORD", "root")
N        = 5

TABLES_SQL = """
CREATE TABLE IF NOT EXISTS items (
    item_id       INT          NOT NULL,
    seller_id     INT          NOT NULL,
    item_name     VARCHAR(32),
    category      INT,
    condition_type ENUM('new', 'used'),
    price         FLOAT,
    quantity      INT,
    thumbs_up     INT DEFAULT 0,
    thumbs_down   INT DEFAULT 0,
    PRIMARY KEY (item_id)
);

CREATE TABLE IF NOT EXISTS item_keywords (
    item_id INT,
    keyword VARCHAR(8),
    FOREIGN KEY (item_id) REFERENCES items(item_id)
);

CREATE TABLE IF NOT EXISTS cart (
    buyer_id INT,
    item_id  INT,
    quantity INT,
    saved    BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (buyer_id, item_id),
    FOREIGN KEY (item_id) REFERENCES items(item_id)
);

CREATE TABLE IF NOT EXISTS purchases (
    buyer_id  INT,
    item_id   INT,
    quantity  INT          NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categories (
    category_id   INT PRIMARY KEY,
    category_name VARCHAR(32) NOT NULL
);
"""

SEED_SQL = """
INSERT IGNORE INTO items
    (item_id, seller_id, item_name, category, condition_type, price, quantity, thumbs_up, thumbs_down)
VALUES
    (1, 1, 'iPhone 12',      1, 'used', 599.99,  3, 5, 1),
    (2, 1, 'MacBook Air',    1, 'used', 899.50,  2, 8, 0),
    (3, 2, 'Office Chair',   2, 'new',  129.99, 10, 2, 0),
    (4, 2, 'Study Table',    2, 'used',  89.99,  5, 1, 1),
    (5, 3, 'Wireless Mouse', 3, 'new',   19.99, 25, 0, 0);

INSERT IGNORE INTO item_keywords (item_id, keyword) VALUES
    (1, 'phone'), (1, 'apple'), (1, 'ios'),
    (2, 'laptop'), (2, 'apple'), (2, 'mac'),
    (3, 'chair'), (3, 'office'), (3, 'seat'),
    (4, 'table'), (4, 'desk'), (4, 'study'),
    (5, 'mouse'), (5, 'wireless'), (5, 'usb');

INSERT IGNORE INTO categories (category_id, category_name) VALUES
    (1, 'Electronics'),
    (2, 'Furniture'),
    (3, 'Accessories'),
    (4, 'Books'),
    (5, 'Clothing');
"""


def run(cursor, sql: str, label: str = ""):
    for statement in sql.strip().split(";"):
        statement = statement.strip()
        if statement:
            cursor.execute(statement)
    if label:
        print(f"  Checked: {label}")


def setup_replica(conn, db_name: str, drop: bool, seed: bool):
    cur = conn.cursor()

    if drop:
        cur.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
        print(f"  Dropped `{db_name}`")

    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
    cur.execute(f"USE `{db_name}`")

    run(cur, TABLES_SQL, "tables")

    if seed:
        run(cur, SEED_SQL, "seed data")

    conn.commit()
    cur.close()


def main():
    parser = argparse.ArgumentParser(description="Set up PA3 product DB replicas")
    parser.add_argument("--drop",    action="store_true", help="Drop existing DBs before recreating")
    parser.add_argument("--no-seed", action="store_true", help="Skip seed data insertion")
    args = parser.parse_args()

    print(f"\nConnecting to MySQL at {USER}@{HOST}:{PORT} ...")
    try:
        conn = mysql.connector.connect(
            host=HOST, port=PORT, user=USER, password=PASSWORD,
        )
    except mysql.connector.Error as exc:
        print(f"\n[ERROR] Cannot connect to MySQL: {exc}")
        print("Check PRODUCT_DB_HOST/PORT/USER/PASSWORD in your .env file.")
        sys.exit(1)

    print("Connected.\n")

    for i in range(N):
        db_name = f"product_db_{i}"
        print(f"Setting up `{db_name}` …")
        try:
            setup_replica(conn, db_name, drop=args.drop, seed=not args.no_seed)
            print(f"  -> done\n")
        except mysql.connector.Error as exc:
            print(f"  [ERROR] {exc}\n")
            conn.rollback()

    conn.close()
    print("=" * 50)
    print(f"All {N} product DB replicas ready.")
    print("=" * 50)


if __name__ == "__main__":
    main()
