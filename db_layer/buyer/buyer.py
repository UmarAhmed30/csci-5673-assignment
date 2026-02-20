import grpc
from concurrent import futures
import buyer_pb2
import buyer_pb2_grpc
import sys
from pathlib import Path
import uuid
import time

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from db_layer.buyer.config import BUYER_SERVER_CONFIG, BUYER_GRPC_CONFIG
from db.client import CustomerDBClient, ProductDBClient

SESSION_TIMEOUT_SECS = BUYER_SERVER_CONFIG["session_timeout_secs"]

customer_db = CustomerDBClient()
product_db = ProductDBClient()


class BuyerServicer(buyer_pb2_grpc.BuyerServiceServicer):
    def CreateBuyer(self, request, context):
        buyer_id, message = create_buyer(request.username, request.password)
        return buyer_pb2.CreateBuyerResponse(
            buyer_id=buyer_id if buyer_id is not None else 0,
            message=message
        )

    def LoginBuyer(self, request, context):
        session_id = login_buyer(request.username, request.password)
        return buyer_pb2.LoginBuyerResponse(
            session_id=session_id if session_id is not None else ""
        )

    def LogoutBuyer(self, request, context):
        logout_session(request.session_id)
        return buyer_pb2.LogoutBuyerResponse()

    def ValidateSession(self, request, context):
        user_id = validate_session(request.session_id)
        return buyer_pb2.ValidateSessionResponse(
            user_id=user_id if user_id is not None else 0
        )

    def TouchSession(self, request, context):
        touch_session(request.session_id)
        return buyer_pb2.TouchSessionResponse()

    def SearchItems(self, request, context):
        rows = search_items(request.category, list(request.keywords))
        items = [
            buyer_pb2.Item(
                item_id=row["item_id"],
                item_name=row["item_name"],
                category=row["category"],
                condition_type=row["condition_type"],
                price=row["price"],
                quantity=row["quantity"],
                thumbs_up=row["thumbs_up"],
                thumbs_down=row["thumbs_down"]
            )
            for row in rows
        ]
        return buyer_pb2.SearchItemsResponse(items=items)

    def GetItem(self, request, context):
        row = get_item(request.item_id)
        if not row:
            return buyer_pb2.GetItemResponse(
                success=False,
                message="Item not found"
            )
        return buyer_pb2.GetItemResponse(
            success=True,
            item=buyer_pb2.Item(
                item_id=row["item_id"],
                item_name=row["item_name"],
                category=row["category"],
                condition_type=row["condition_type"],
                price=row["price"],
                quantity=row["quantity"],
                thumbs_up=row["thumbs_up"],
                thumbs_down=row["thumbs_down"]
            ),
            message="OK"
        )

    def AddToCart(self, request, context):
        success, message = add_to_cart(request.buyer_id, request.item_id, request.quantity)
        return buyer_pb2.AddToCartResponse(success=success, message=message)

    def RemoveFromCart(self, request, context):
        success, message = remove_from_cart(request.buyer_id, request.item_id, request.quantity)
        return buyer_pb2.RemoveFromCartResponse(success=success, message=message)

    def GetCart(self, request, context):
        rows = get_cart(request.buyer_id)
        cart_items = [
            buyer_pb2.CartItem(
                item_id=row["item_id"],
                quantity=row["quantity"],
                saved=bool(row["saved"])
            )
            for row in rows
        ]
        return buyer_pb2.GetCartResponse(items=cart_items)

    def ClearCart(self, request, context):
        clear_cart(request.buyer_id)
        return buyer_pb2.ClearCartResponse()

    def SaveCart(self, request, context):
        success, message = save_cart(request.buyer_id)
        return buyer_pb2.SaveCartResponse(success=success, message=message)

    def ProvideItemFeedback(self, request, context):
        success, message = provide_item_feedback(request.item_id, request.feedback)
        return buyer_pb2.ProvideItemFeedbackResponse(success=success, message=message)

    def GetSellerRating(self, request, context):
        row = get_seller_rating(request.seller_id)
        if not row:
            return buyer_pb2.GetSellerRatingResponse(
                success=False,
                message="Seller not found"
            )
        return buyer_pb2.GetSellerRatingResponse(
            success=True,
            thumbs_up=row["thumbs_up"],
            thumbs_down=row["thumbs_down"],
            message="OK"
        )

    def GetBuyerPurchases(self, request, context):
        rows = get_buyer_purchases(request.buyer_id)
        purchases = [
            buyer_pb2.Purchase(
                item_id=row["item_id"],
                timestamp=str(row["timestamp"]),
                quantity=row["quantity"]
            )
            for row in rows
        ]
        return buyer_pb2.GetBuyerPurchasesResponse(purchases=purchases)

    def MakePurchase(self, request, context):
        cart_items = [
            {"item_id": item.item_id, "quantity": item.quantity}
            for item in request.cart_items
        ]
        success, message = make_purchase(request.buyer_id, cart_items)
        items_purchased = len(cart_items) if success else 0
        return buyer_pb2.MakePurchaseResponse(
            success=success,
            message=message,
            items_purchased=items_purchased
        )


# --- db functions unchanged below ---

def create_buyer(username, password):
    if len(username) > 32:
        return None, "Username must be 32 characters or less"
    conn = customer_db.get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO buyers (buyer_name, password) VALUES (%s, %s)",
            (username, password),
        )
        buyer_id = cur.lastrowid
        conn.commit()
        cur.close()
        conn.close()
        return buyer_id, "OK"
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return None, str(e)


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
    conn.commit()
    cur.close()
    conn.close()
    return session_id


def logout_session(session_id):
    conn = customer_db.get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT user_id FROM sessions WHERE session_id=%s AND user_type='buyer'",
        (session_id,),
    )
    row = cur.fetchone()
    buyer_id = row["user_id"] if row else None
    cur.execute(
        "DELETE FROM sessions WHERE session_id=%s",
        (session_id,),
    )
    conn.commit()
    cur.close()
    conn.close()
    if buyer_id:
        clear_unsaved_cart(buyer_id)


def clear_unsaved_cart(buyer_id):
    conn = product_db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM cart WHERE buyer_id = %s AND saved = FALSE",
        (buyer_id,),
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
        logout_session(session_id)
        return None
    return row["user_id"]


def touch_session(session_id):
    conn = customer_db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE sessions SET last_active=NOW() WHERE session_id=%s",
        (session_id,),
    )
    conn.commit()
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
    if not isinstance(item_id, int) or item_id <= 0:
        return None
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
    if not isinstance(item_id, int) or item_id <= 0:
        return False, "Item ID must be a positive integer"
    if not isinstance(qty, int) or qty <= 0:
        return False, "Quantity must be a positive integer"
    conn = product_db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT quantity FROM items WHERE item_id=%s",
        (item_id,),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return False, "Item not found"
    available_qty = row[0]
    cur.execute(
        "SELECT quantity FROM cart WHERE buyer_id=%s AND item_id=%s",
        (buyer_id, item_id),
    )
    cart_row = cur.fetchone()
    current_cart_qty = cart_row[0] if cart_row else 0
    total_requested = current_cart_qty + qty
    if total_requested > available_qty:
        cur.close()
        conn.close()
        return False, f"Insufficient quantity. Available: {available_qty}, In cart: {current_cart_qty}, Requested: {qty}"
    cur.execute(
        "INSERT INTO cart (buyer_id, item_id, quantity, saved) "
        "VALUES (%s, %s, %s, FALSE) "
        "ON DUPLICATE KEY UPDATE quantity = quantity + %s, saved = FALSE",
        (buyer_id, item_id, qty, qty),
    )
    conn.commit()
    cur.close()
    conn.close()
    return True, "OK"


def remove_from_cart(buyer_id, item_id, qty):
    if not isinstance(item_id, int) or item_id <= 0:
        return False, "Item ID must be a positive integer"
    if not isinstance(qty, int) or qty <= 0:
        return False, "Quantity must be a positive integer"
    conn = product_db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT quantity FROM cart WHERE buyer_id=%s AND item_id=%s",
        (buyer_id, item_id),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return False, "Item not in cart"
    current_qty = row[0]
    if qty > current_qty:
        cur.close()
        conn.close()
        return False, f"Cannot remove {qty} items. Only {current_qty} in cart"
    if qty == current_qty:
        cur.execute(
            "DELETE FROM cart WHERE buyer_id=%s AND item_id=%s",
            (buyer_id, item_id),
        )
    else:
        cur.execute(
            "UPDATE cart SET quantity = quantity - %s, saved = FALSE "
            "WHERE buyer_id=%s AND item_id=%s",
            (qty, buyer_id, item_id),
        )
    conn.commit()
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
    conn.commit()
    cur.close()
    conn.close()


def get_cart(buyer_id):
    conn = product_db.get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT item_id, quantity, saved FROM cart WHERE buyer_id=%s",
        (buyer_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def save_cart(buyer_id):
    conn = product_db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE cart SET saved = TRUE WHERE buyer_id = %s",
        (buyer_id,),
    )
    rows_affected = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return True, f"{rows_affected} items saved"


def provide_item_feedback(item_id, feedback):
    if not isinstance(item_id, int) or item_id <= 0:
        return False, "Item ID must be a positive integer"
    if feedback not in ("up", "down"):
        return False, "Feedback must be either 'up' or 'down'"
    conn = product_db.get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT item_id FROM items WHERE item_id=%s",
        (item_id,),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return False, "Item not found"
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
    conn.commit()
    cur.close()
    conn.close()
    return True, "Feedback recorded"


def get_seller_rating(seller_id):
    if not isinstance(seller_id, int) or seller_id <= 0:
        return None
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
        "SELECT item_id, quantity, timestamp FROM purchases WHERE buyer_id=%s",
        (buyer_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def make_purchase(buyer_id, cart_items):
    """Record purchase in database and decrease item quantities"""
    conn = product_db.get_connection()
    cur = conn.cursor()
    try:
        for item in cart_items:
            cur.execute(
                "INSERT INTO purchases (buyer_id, item_id, quantity) VALUES (%s, %s, %s)",
                (buyer_id, item["item_id"], item["quantity"])
            )
            # Decrease item quantity
            cur.execute(
                "UPDATE items SET quantity = quantity - %s WHERE item_id = %s",
                (item["quantity"], item["item_id"])
            )
        conn.commit()
        cur.close()
        conn.close()
        return True, f"{len(cart_items)} items purchased"
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return False, str(e)


def serve():
    host = BUYER_GRPC_CONFIG["host"]
    port = BUYER_GRPC_CONFIG["port"]
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    buyer_pb2_grpc.add_BuyerServiceServicer_to_server(BuyerServicer(), server)
    server.add_insecure_port(f"{host}:{port}")
    server.start()
    print(f"Buyer gRPC Server started on {host}:{port}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
