import sys
from pathlib import Path
import uuid
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from server.buyer.config import BUYER_SERVER_CONFIG
from db.client import CustomerDBClient, ProductDBClient

SESSION_TIMEOUT_SECS = BUYER_SERVER_CONFIG["session_timeout_secs"]


customer_db = CustomerDBClient()
product_db = ProductDBClient()


def create_buyer(username, password):
    conn = customer_db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO buyers (buyer_name, password) VALUES (%s, %s)",
        (username, password),
    )
    buyer_id = cur.lastrowid
    cur.close()
    conn.close()
    return buyer_id


def login_buyer(username, password):
    conn = customer_db.get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT buyer_id FROM buyers WHERE buyer_name=%s AND password=%s",
        (username, password),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return None
    session_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO sessions (session_id, user_id, user_type)
        VALUES (%s, %s, 'buyer')
        """,
        (session_id, row["buyer_id"]),
    )
    cur.close()
    conn.close()
    return session_id


def logout_session(session_id):
    conn = customer_db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM sessions WHERE session_id=%s",
        (session_id,),
    )
    cur.close()
    conn.close()


def validate_session(session_id):
    if not session_id:
        return None
    conn = customer_db.get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT user_id, UNIX_TIMESTAMP(last_active) AS last_active
        FROM sessions
        WHERE session_id = %s
        AND user_type = 'buyer'
        """,
        (session_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    if time.time() - row["last_active"] > SESSION_TIMEOUT_SECS:
        logout_session(session_id, conn)
        return None
    return row["user_id"]


def touch_session(session_id):
    conn = customer_db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE sessions SET last_active=NOW() WHERE session_id=%s",
        (session_id,),
    )
    cur.close()
    conn.close()


def search_items(category, keywords):
    conn = product_db.get_connection()
    cur = conn.cursor(dictionary=True)
    base_query = """
        SELECT DISTINCT i.*
        FROM items i
        LEFT JOIN item_keywords k ON i.item_id = k.item_id
        WHERE i.category = %s
        AND i.quantity > 0
    """
    params = [category]
    if keywords:
        placeholders = ",".join(["%s"] * len(keywords))
        base_query += f"""
            AND k.keyword IN ({placeholders})
        """
        params.extend(keywords)
    cur.execute(base_query, tuple(params))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def get_item(item_id):
    conn = product_db.get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT * FROM items WHERE item_id=%s",
        (item_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def add_to_cart(buyer_id, item_id, qty):
    conn = product_db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT quantity FROM items WHERE item_id=%s",
        (item_id,),
    )
    row = cur.fetchone()
    if not row or row[0] < qty:
        cur.close()
        conn.close()
        return False, "Insufficient quantity"
    cur.execute(
        "INSERT INTO cart (buyer_id, item_id, quantity) "
        "VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE quantity = quantity + %s",
        (buyer_id, item_id, qty, qty),
    )
    cur.close()
    conn.close()
    return True, "OK"


def remove_from_cart(buyer_id, item_id, qty):
    conn = product_db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT quantity FROM cart WHERE buyer_id=%s AND item_id=%s",
        (buyer_id, item_id),
    )
    row = cur.fetchone()
    if not row or row[0] < qty:
        cur.close()
        conn.close()
        return False, "Not enough items in cart"
    if row[0] == qty:
        cur.execute(
            "DELETE FROM cart WHERE buyer_id=%s AND item_id=%s",
            (buyer_id, item_id),
        )
    else:
        cur.execute(
            "UPDATE cart SET quantity = quantity - %s "
            "WHERE buyer_id=%s AND item_id=%s",
            (qty, buyer_id, item_id),
        )
    cur.close()
    conn.close()
    return True, "OK"


def clear_cart(buyer_id):
    conn = product_db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM cart WHERE buyer_id=%s",
        (buyer_id,),
    )
    cur.close()
    conn.close()


def get_cart(buyer_id):
    conn = product_db.get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT item_id, quantity FROM cart WHERE buyer_id=%s",
        (buyer_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def save_cart(buyer_id):
    return True


def provide_item_feedback(item_id, feedback):
    conn = product_db.get_connection()
    cur = conn.cursor()
    if feedback == "up":
        cur.execute(
            "UPDATE items SET thumbs_up = thumbs_up + 1 WHERE item_id=%s",
            (item_id,),
        )
    else:
        cur.execute(
            "UPDATE items SET thumbs_down = thumbs_down + 1 WHERE item_id=%s",
            (item_id,),
        )
    cur.close()
    conn.close()


def get_seller_rating(seller_id):
    conn = customer_db.get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT thumbs_up, thumbs_down FROM sellers WHERE seller_id=%s",
        (seller_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def get_buyer_purchases(buyer_id):
    conn = product_db.get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT item_id, timestamp FROM purchases WHERE buyer_id=%s",
        (buyer_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows
