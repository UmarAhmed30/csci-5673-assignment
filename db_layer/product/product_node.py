"""
db_layer/product/product_node.py

Raft-replicated product database node using pysyncobj.

Every write method is decorated with @replicated so pysyncobj replicates the
call to all peers before applying it to the local MySQL database.  Callers
MUST pass a `callback` kwarg — pysyncobj delivers the return value (and any
error) through that callback rather than as a function return value.

Usage in product_server.py:
    import threading

    event = threading.Event()
    result_box = [None]

    def cb(res, err):
        result_box[0] = (res, err)
        event.set()

    node.add_to_cart(buyer_id, item_id, quantity, callback=cb)
    event.wait(timeout=10.0)
    res, err = result_box[0]
    if err is not None:
        # surface as gRPC UNAVAILABLE
        ...

Read methods (search_items, get_cart, etc.) are plain methods — they bypass
Raft and query the local MySQL replica directly.
"""

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import mysql.connector
from mysql.connector import pooling
from pysyncobj import SyncObj, SyncObjConf, replicated

from db_layer.product.config import (
    RAFT_SELF_ADDR,
    RAFT_PARTNER_ADDRS,
    PRODUCT_DB_CONFIG,
)


def _make_pool(db_config: dict):
    return pooling.MySQLConnectionPool(
        pool_name="product_raft_pool",
        host=db_config["host"],
        port=db_config["port"],
        user=db_config["user"],
        password=db_config["password"],
        database=db_config["database"],
        autocommit=True,
    )


class ProductRaftNode(SyncObj):
    """
    Raft-replicated node that owns the product_db_N MySQL instance for
    this replica.

    Write operations are decorated with @replicated so they run in global
    Raft order on every peer.  Read operations access local MySQL directly.
    """

    def __init__(self, self_addr: str, partner_addrs: list, db_config: dict):
        cfg = SyncObjConf(
            logCompactionMinEntries=10**9,
            logCompactionMinTime=10**9,
        )
        super().__init__(self_addr, partner_addrs, cfg)
        self._pool = _make_pool(db_config)

    def _conn(self):
        return self._pool.get_connection()

    # -----------------------------------------------------------------------
    # Write operations — replicated via Raft
    # -----------------------------------------------------------------------

    @replicated
    def add_to_cart(self, buyer_id: int, item_id: int, quantity: int):
        conn = self._conn()
        cur = conn.cursor()
        try:
            cur.execute("SELECT quantity FROM items WHERE item_id=%s", (item_id,))
            row = cur.fetchone()
            if not row:
                return False, "Item not found"
            available = row[0]
            cur.execute(
                "SELECT quantity FROM cart WHERE buyer_id=%s AND item_id=%s",
                (buyer_id, item_id),
            )
            cart_row = cur.fetchone()
            in_cart = cart_row[0] if cart_row else 0
            if in_cart + quantity > available:
                return (
                    False,
                    f"Insufficient quantity. Available: {available}, "
                    f"In cart: {in_cart}, Requested: {quantity}",
                )
            cur.execute(
                "INSERT INTO cart (buyer_id, item_id, quantity, saved) "
                "VALUES (%s, %s, %s, FALSE) "
                "ON DUPLICATE KEY UPDATE quantity = quantity + %s, saved = FALSE",
                (buyer_id, item_id, quantity, quantity),
            )
            conn.commit()
            return True, "OK"
        except Exception as exc:
            conn.rollback()
            return False, str(exc)
        finally:
            cur.close()
            conn.close()

    @replicated
    def remove_from_cart(self, buyer_id: int, item_id: int, quantity: int):
        conn = self._conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT quantity FROM cart WHERE buyer_id=%s AND item_id=%s",
                (buyer_id, item_id),
            )
            row = cur.fetchone()
            if not row:
                return False, "Item not in cart"
            current = row[0]
            if quantity > current:
                return False, f"Cannot remove {quantity} items. Only {current} in cart"
            if quantity == current:
                cur.execute(
                    "DELETE FROM cart WHERE buyer_id=%s AND item_id=%s",
                    (buyer_id, item_id),
                )
            else:
                cur.execute(
                    "UPDATE cart SET quantity = quantity - %s, saved = FALSE "
                    "WHERE buyer_id=%s AND item_id=%s",
                    (quantity, buyer_id, item_id),
                )
            conn.commit()
            return True, "OK"
        except Exception as exc:
            conn.rollback()
            return False, str(exc)
        finally:
            cur.close()
            conn.close()

    @replicated
    def clear_cart(self, buyer_id: int):
        conn = self._conn()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM cart WHERE buyer_id=%s", (buyer_id,))
            conn.commit()
        finally:
            cur.close()
            conn.close()

    @replicated
    def clear_unsaved_cart(self, buyer_id: int):
        conn = self._conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "DELETE FROM cart WHERE buyer_id=%s AND saved = FALSE", (buyer_id,)
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()

    @replicated
    def save_cart(self, buyer_id: int):
        conn = self._conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE cart SET saved = TRUE WHERE buyer_id = %s", (buyer_id,)
            )
            affected = cur.rowcount
            conn.commit()
            return True, f"{affected} items saved"
        except Exception as exc:
            conn.rollback()
            return False, str(exc)
        finally:
            cur.close()
            conn.close()

    @replicated
    def provide_item_feedback(self, item_id: int, feedback: str):
        conn = self._conn()
        cur = conn.cursor()
        try:
            cur.execute("SELECT item_id FROM items WHERE item_id=%s", (item_id,))
            if not cur.fetchone():
                return False, "Item not found"
            col = "thumbs_up" if feedback == "up" else "thumbs_down"
            cur.execute(
                f"UPDATE items SET {col} = {col} + 1 WHERE item_id=%s", (item_id,)
            )
            conn.commit()
            return True, "Feedback recorded"
        except Exception as exc:
            conn.rollback()
            return False, str(exc)
        finally:
            cur.close()
            conn.close()

    @replicated
    def make_purchase(self, buyer_id: int, cart_items: list):
        """
        cart_items: list of {"item_id": int, "quantity": int}
        Inserts purchase rows and decrements item quantities atomically.
        """
        conn = self._conn()
        cur = conn.cursor()
        try:
            for item in cart_items:
                cur.execute(
                    "INSERT INTO purchases (buyer_id, item_id, quantity) "
                    "VALUES (%s, %s, %s)",
                    (buyer_id, item["item_id"], item["quantity"]),
                )
                cur.execute(
                    "UPDATE items SET quantity = quantity - %s WHERE item_id = %s",
                    (item["quantity"], item["item_id"]),
                )
            conn.commit()
            return True, f"{len(cart_items)} items purchased"
        except Exception as exc:
            conn.rollback()
            return False, str(exc)
        finally:
            cur.close()
            conn.close()

    @replicated
    def register_item(
        self,
        item_id: int,
        seller_id: int,
        item_name: str,
        category: int,
        condition_type: str,
        price: float,
        quantity: int,
        keywords: list,
    ):
        """
        item_id is pre-generated by the caller so all replicas insert the same row.
        """
        conn = self._conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO items "
                "(item_id, seller_id, item_name, category, condition_type, price, quantity) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (item_id, seller_id, item_name, category, condition_type, price, quantity),
            )
            for kw in keywords:
                cur.execute(
                    "INSERT INTO item_keywords (item_id, keyword) VALUES (%s, %s)",
                    (item_id, kw),
                )
            conn.commit()
            return True, item_id, "OK"
        except Exception as exc:
            conn.rollback()
            return False, 0, str(exc)
        finally:
            cur.close()
            conn.close()

    @replicated
    def update_units_for_sale(self, seller_id: int, item_id: int, quantity: int):
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                "SELECT quantity FROM items WHERE item_id=%s AND seller_id=%s",
                (item_id, seller_id),
            )
            row = cur.fetchone()
            if not row:
                return False, "Item not found or does not belong to you"
            current = row["quantity"]
            if quantity > current:
                return False, f"Cannot remove {quantity} units. Only {current} available"
            cur.execute(
                "UPDATE items SET quantity=%s WHERE item_id=%s AND seller_id=%s",
                (current - quantity, item_id, seller_id),
            )
            conn.commit()
            return True, f"Removed {quantity} units. New quantity: {current - quantity}"
        except Exception as exc:
            conn.rollback()
            return False, str(exc)
        finally:
            cur.close()
            conn.close()

    @replicated
    def change_item_price(self, seller_id: int, item_id: int, price: float):
        conn = self._conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE items SET price=%s WHERE item_id=%s AND seller_id=%s",
                (price, item_id, seller_id),
            )
            conn.commit()
            return True, "UPDATED"
        except Exception as exc:
            conn.rollback()
            return False, str(exc)
        finally:
            cur.close()
            conn.close()

    # -----------------------------------------------------------------------
    # Read operations — direct local MySQL, no Raft
    # -----------------------------------------------------------------------

    def search_items(self, category: int, keywords: list):
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        try:
            base = (
                "SELECT DISTINCT i.* FROM items i "
                "LEFT JOIN item_keywords k ON i.item_id = k.item_id "
                "WHERE i.category = %s AND i.quantity > 0"
            )
            params = [category]
            if keywords:
                placeholders = ",".join(["%s"] * len(keywords))
                base += f" AND k.keyword IN ({placeholders})"
                params.extend(keywords)
            cur.execute(base, tuple(params))
            return cur.fetchall()
        finally:
            cur.close()
            conn.close()

    def get_item(self, item_id: int):
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute("SELECT * FROM items WHERE item_id=%s", (item_id,))
            return cur.fetchone()
        finally:
            cur.close()
            conn.close()

    def get_cart(self, buyer_id: int):
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                "SELECT item_id, quantity, saved FROM cart WHERE buyer_id=%s",
                (buyer_id,),
            )
            return cur.fetchall()
        finally:
            cur.close()
            conn.close()

    def get_buyer_purchases(self, buyer_id: int):
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                "SELECT item_id, quantity, timestamp FROM purchases WHERE buyer_id=%s",
                (buyer_id,),
            )
            return cur.fetchall()
        finally:
            cur.close()
            conn.close()

    def display_items(self, seller_id: int):
        conn = self._conn()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                "SELECT item_id, seller_id, item_name, category, condition_type, "
                "price, quantity, thumbs_up, thumbs_down "
                "FROM items WHERE seller_id=%s",
                (seller_id,),
            )
            return cur.fetchall()
        finally:
            cur.close()
            conn.close()


def make_node(db_config: Optional[dict] = None) -> ProductRaftNode:
    """Factory used by product_server.py."""
    if db_config is None:
        db_config = PRODUCT_DB_CONFIG
    return ProductRaftNode(RAFT_SELF_ADDR, RAFT_PARTNER_ADDRS, db_config)
