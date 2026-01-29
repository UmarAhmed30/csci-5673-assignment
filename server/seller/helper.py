import sys
from pathlib import Path
import uuid
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from server.seller.config import SELLER_SERVER_CONFIG
from db.client import CustomerDBClient, ProductDBClient

SESSION_TIMEOUT_SECS = SELLER_SERVER_CONFIG["session_timeout_secs"]


customer_db = CustomerDBClient()
product_db = ProductDBClient()


def create_seller(username, password):
    if len(username) > 32:
        return None, "Username must be 32 characters or less"
    conn = customer_db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO sellers (seller_name, password) VALUES (%s, %s)",
        (username, password),
    )
    seller_id = cur.lastrowid
    conn.commit()
    cur.close()
    conn.close()
    return seller_id, "OK"


def login_seller(username, password):
    conn = customer_db.get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT seller_id FROM sellers WHERE seller_name=%s AND password=%s",
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
        VALUES (%s, %s, 'seller')
        """,
        (session_id, row["seller_id"]),
    )
    conn.commit()
    cur.close()
    conn.close()
    return session_id


def logout_seller(session_id):
    conn = customer_db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM sessions WHERE session_id=%s AND user_type='seller'",
        (session_id,),
    )
    conn.commit()
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
        AND user_type = 'seller'
        """,
        (session_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    if time.time() - row["last_active"] > SESSION_TIMEOUT_SECS:
        logout_seller(session_id)
        return None
    return row["user_id"]


def touch_session(session_id):
    conn = customer_db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE sessions SET last_active=NOW() WHERE session_id=%s AND user_type = 'seller'",
        (session_id,),
    )
    conn.commit()
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

def register_item_for_sale(seller_id, item_name, item_category, condition_type, salePrice, quantity, keywords):
    if len(item_name) > 32:
        return False, "Item name must be 32 characters or less"
    try:
        item_category = int(item_category)
        quantity = int(quantity)
        salePrice = float(salePrice)
    except (ValueError, TypeError):
        return False, "Invalid category, quantity, or price format"
    if item_category <= 0:
        return False, "Category must be a positive integer"
    if quantity <= 0:
        return False, "Quantity must be a positive integer"
    if salePrice <= 0:
        return False, "Price must be a positive number"
    for kw in keywords:
        if len(kw) > 8:
            return False, "Keyword length must be <= 8 characters"
    print("reached register item for sale")
    conn = product_db.get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "INSERT INTO items (seller_id, item_name, category, condition_type, price, quantity) VALUES (%s, %s, %s, %s, %s, %s)",
        (seller_id, item_name,item_category, condition_type, salePrice,quantity),
    )
    item_id = cur.lastrowid
    print(f"Item inserted with ID {item_id}")

    insert_keyword_query = """
    INSERT INTO item_keywords (item_id, keyword)
    VALUES (%s, %s);
    """

    for kw in keywords:
        cur.execute(insert_keyword_query, (item_id, kw))
    
    print(f"{len(keywords)} keywords inserted for item {item_id}")
    conn.commit()
    cur.close()
    conn.close()
    return True, {"item_id": item_id}


def display_items_for_sale(seller_id):
    conn = product_db.get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT  item_id, item_name, category, condition_type, price, quantity, thumbs_up, thumbs_down from items where seller_id=%s",
        (seller_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def update_units_for_sale(seller_id, item_id, quantity):
    if not isinstance(item_id, int) or item_id <= 0:
        return False, "Item ID must be a positive integer"
    if not isinstance(quantity, int) or quantity <= 0:
        return False, "Quantity to remove must be a positive integer"
    conn = product_db.get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT quantity FROM items WHERE category_id=%s AND item_id=%s AND seller_id=%s",
        (category_id, item_id, seller_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return False, "Item not found or does not belong to you"
    current_quantity = row['quantity']
    if quantity > current_quantity:
        cur.close()
        conn.close()
        return False, f"Cannot remove {quantity} units. Only {current_quantity} available"
    new_quantity = current_quantity - quantity
    cur.execute(
        "UPDATE items SET quantity=%s WHERE category_id=%s AND item_id=%s AND seller_id=%s",
        (new_quantity, category_id, item_id, seller_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return True, f"Removed {quantity} units. New quantity: {new_quantity}"

def change_item_price(seller_id, item_id, price):
    conn = product_db.get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "UPDATE  items SET price=%s WHERE item_id=%s AND seller_id=%s",
        (price,item_id,seller_id,),
    )
    print(cur.rowcount," updated")
    conn.commit()
    cur.close()
    conn.close()
    return True, "UPDATED"
