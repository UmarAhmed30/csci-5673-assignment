"""
db/setup_pa3_replicas.py

Creates the five customer_db replicas (customer_db_0 … customer_db_4) required
for PA3 atomic broadcast replication.

Each replica gets the same schema as the original customer_db:
    - buyers   (buyer_id NOT NULL — broadcast layer inserts explicit pre-generated IDs)
    - sellers  (seller_id NOT NULL — broadcast layer inserts explicit pre-generated IDs)
    - sessions

Reads MySQL credentials from .env (same vars as the rest of the codebase).

Usage:
    cd <project root>
    python db/setup_pa3_replicas.py

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

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

HOST     = os.getenv("CUSTOMER_DB_HOST", "localhost")
PORT     = int(os.getenv("CUSTOMER_DB_PORT", "3306"))
USER     = os.getenv("CUSTOMER_DB_USER", "root")
PASSWORD = os.getenv("CUSTOMER_DB_PASSWORD", "root")
N        = 5   # number of replicas

# ---------------------------------------------------------------------------
# DDL — one set of statements per database
# ---------------------------------------------------------------------------

TABLES_SQL = """
CREATE TABLE IF NOT EXISTS buyers (
    buyer_id   INT          NOT NULL,
    buyer_name VARCHAR(32)  NOT NULL,
    password   VARCHAR(64)  NOT NULL,
    items_purchased INT DEFAULT 0,
    PRIMARY KEY (buyer_id)
);

CREATE TABLE IF NOT EXISTS sellers (
    seller_id   INT         NOT NULL,
    seller_name VARCHAR(32) NOT NULL,
    password    VARCHAR(64) NOT NULL,
    thumbs_up   INT DEFAULT 0,
    thumbs_down INT DEFAULT 0,
    items_sold  INT DEFAULT 0,
    PRIMARY KEY (seller_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id CHAR(36) PRIMARY KEY,
    user_id    INT      NOT NULL,
    user_type  ENUM('buyer', 'seller') NOT NULL,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);
"""

# Stub data identical to the original schema.sql so the existing test clients work.
SEED_SQL = """
INSERT IGNORE INTO sellers (seller_id, seller_name, password, thumbs_up, thumbs_down, items_sold)
VALUES
    (1, 'Seller1', 'seller1', 10, 1, 5),
    (2, 'Seller2', 'seller2',  3, 0, 2),
    (3, 'Seller3', 'seller3',  0, 0, 0);
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(cursor, sql: str, label: str = ""):
    for statement in sql.strip().split(";"):
        statement = statement.strip()
        if statement:
            cursor.execute(statement)
    if label:
        print(f"Checked: {label}")


def setup_replica(conn, db_name: str, drop: bool, seed: bool):
    cur = conn.cursor()

    if drop:
        cur.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
        print(f"dropped `{db_name}`")

    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
    cur.execute(f"USE `{db_name}`")

    run(cur, TABLES_SQL, "tables created")

    if seed:
        run(cur, SEED_SQL, "seed data inserted")

    conn.commit()
    cur.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Set up PA3 customer DB replicas")
    parser.add_argument("--drop",    action="store_true", help="Drop existing DBs before recreating")
    parser.add_argument("--no-seed", action="store_true", help="Skip seed data insertion")
    args = parser.parse_args()

    print(f"\nConnecting to MySQL at {USER}@{HOST}:{PORT} …")
    try:
        conn = mysql.connector.connect(
            host=HOST,
            port=PORT,
            user=USER,
            password=PASSWORD,
        )
    except mysql.connector.Error as exc:
        print(f"\n[ERROR] Cannot connect to MySQL: {exc}")
        print("Check CUSTOMER_DB_HOST/PORT/USER/PASSWORD in your .env file.")
        sys.exit(1)

    print(f"Connected.\n")

    for i in range(N):
        db_name = f"customer_db_{i}"
        print(f"Setting up `{db_name}` …")
        try:
            setup_replica(conn, db_name, drop=args.drop, seed=not args.no_seed)
            print(f"  → done\n")
        except mysql.connector.Error as exc:
            print(f"  [ERROR] {exc}\n")
            conn.rollback()

    conn.close()

    print("=" * 50)
    print(f"All {N} customer DB replicas ready.")
    print("=" * 50)


if __name__ == "__main__":
    main()
