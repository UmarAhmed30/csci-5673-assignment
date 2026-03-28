import grpc
from concurrent import futures
import seller_pb2
import seller_pb2_grpc
import sys
from pathlib import Path
import uuid
import random
import time

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from db_layer.seller.config import SELLER_SERVER_CONFIG, SELLER_GRPC_CONFIG
from db.client import CustomerDBClient, ProductDBClient
from broadcast.node import BroadcastNode

SESSION_TIMEOUT_SECS = SELLER_SERVER_CONFIG["session_timeout_secs"]

customer_db = CustomerDBClient()
product_db = ProductDBClient()


# ---------------------------------------------------------------------------
# Broadcast node — started in serve(), used by SellerServicer write methods
# ---------------------------------------------------------------------------

def apply_operation(payload: dict):
    """
    Delivery callback invoked by BroadcastNode._delivery_loop for each
    committed write operation, in global sequence order.

    Returns a value that is forwarded to the waiting gRPC thread via a Future.
    Raises on unrecoverable failure.
    """
    op   = payload["op"]
    args = payload["args"]

    if op == "create_seller":
        return create_seller_replicated(
            args["seller_id"], args["username"], args["password"]
        )
    if op == "login_seller":
        return login_seller_replicated(
            args["username"], args["password"], args["session_id"]
        )
    if op == "logout_session":
        return delete_seller_session_replicated(args["session_id"])
    if op == "touch_session":
        touch_session(args["session_id"])
        return None

    raise ValueError(f"apply_operation: unknown op {op!r}")


broadcast_node: BroadcastNode = BroadcastNode(apply_fn=apply_operation)


def _wait_for_read_consistency():
    """
    Block the calling thread until all pending Sequence messages in the
    broadcast store have been delivered and applied to the local DB.

    This prevents stale reads, mirroring the buyer implementation.
    """
    while broadcast_node.has_pending_deliveries():
        time.sleep(0.001)


# ---------------------------------------------------------------------------
# gRPC servicer
# ---------------------------------------------------------------------------

class SellerServicer(seller_pb2_grpc.SellerServiceServicer):

    # -- writes that touch customer_db → go through atomic broadcast ----------

    def CreateSeller(self, request, context):
        # Pre-generate seller_id so every replica inserts the same value.
        new_seller_id = random.randint(1, 2**31 - 1)
        result = broadcast_node.broadcast_request({
            "op": "create_seller",
            "args": {
                "seller_id": new_seller_id,
                "username":  request.username,
                "password":  request.password,
            },
        })
        seller_id, message = result
        return seller_pb2.CreateSellerResponse(
            seller_id=seller_id if seller_id is not None else 0,
            message=message,
        )

    def LoginSeller(self, request, context):
        # Pre-generate session_id so every replica inserts the same session row.
        session_id = str(uuid.uuid4())
        result = broadcast_node.broadcast_request({
            "op": "login_seller",
            "args": {
                "username":   request.username,
                "password":   request.password,
                "session_id": session_id,
            },
        })
        return seller_pb2.LoginSellerResponse(
            session_id=result if result is not None else ""
        )

    def LogoutSeller(self, request, context):
        broadcast_node.broadcast_request({
            "op": "logout_session",
            "args": {"session_id": request.session_id},
        })
        return seller_pb2.LogoutSellerResponse()

    def TouchSession(self, request, context):
        broadcast_node.broadcast_request({
            "op": "touch_session",
            "args": {"session_id": request.session_id},
        })
        return seller_pb2.TouchSessionResponse()

    # -- reads from customer_db → wait for consistency first -----------------

    def ValidateSession(self, request, context):
        _wait_for_read_consistency()
        user_id = validate_session(request.session_id)
        return seller_pb2.ValidateSessionResponse(
            user_id=user_id if user_id is not None else 0
        )

    def GetSellerRating(self, request, context):
        _wait_for_read_consistency()
        row = get_seller_rating(request.seller_id)
        if not row:
            return seller_pb2.GetSellerRatingResponse(thumbs_up=0, thumbs_down=0)
        return seller_pb2.GetSellerRatingResponse(
            thumbs_up=row["thumbs_up"],
            thumbs_down=row["thumbs_down"],
        )

    # -- product_db operations → direct (Raft scope, not broadcast) ----------

    def RegisterItem(self, request, context):
        success, result = register_item_for_sale(
            request.seller_id,
            request.item_name,
            request.item_category,
            request.condition_type,
            request.sale_price,
            request.quantity,
            list(request.keywords)
        )
        if not success:
            return seller_pb2.RegisterItemResponse(success=False, item_id=0, message=result)
        return seller_pb2.RegisterItemResponse(success=True, item_id=result["item_id"], message="OK")

    def DisplayItems(self, request, context):
        rows = display_items_for_sale(request.seller_id)
        items = [
            seller_pb2.Item(
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
        return seller_pb2.DisplayItemsResponse(items=items)

    def UpdateUnitsForSale(self, request, context):
        success, message = update_units_for_sale(request.seller_id, request.item_id, request.quantity)
        return seller_pb2.UpdateUnitsForSaleResponse(success=success, message=message)

    def ChangeItemPrice(self, request, context):
        success, message = change_item_price(request.seller_id, request.item_id, request.price)
        return seller_pb2.ChangeItemPriceResponse(success=success, message=message)


# ---------------------------------------------------------------------------
# customer_db write functions — replicated variants (called via apply_fn)
# ---------------------------------------------------------------------------

def create_seller_replicated(seller_id, username, password):
    """
    Insert a seller with a pre-determined seller_id so all replicas produce
    the same row.  The caller (broadcast originator) pre-generates the ID.
    """
    if len(username) > 32:
        return None, "Username must be 32 characters or less"
    conn = customer_db.get_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO sellers (seller_id, seller_name, password) VALUES (%s, %s, %s)",
            (seller_id, username, password),
        )
        conn.commit()
        cur.close()
        conn.close()
        return seller_id, "OK"
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return None, str(e)


def login_seller_replicated(username, password, session_id):
    """
    Validate credentials and insert the pre-determined session_id so all
    replicas insert the same session row.
    Returns session_id on success, None on bad credentials.
    """
    conn = customer_db.get_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT seller_id FROM sellers WHERE seller_name=%s AND password=%s",
        (username, password),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return None
    try:
        cur.execute(
            "INSERT INTO sessions (session_id, user_id, user_type) "
            "VALUES (%s, %s, 'seller')",
            (session_id, row["seller_id"]),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        cur.close()
        conn.close()
        return None
    cur.close()
    conn.close()
    return session_id


def delete_seller_session_replicated(session_id):
    """
    Delete the session row from customer_db (user_type='seller').
    """
    conn = customer_db.get_connection()
    cur  = conn.cursor()
    cur.execute(
        "DELETE FROM sessions WHERE session_id=%s AND user_type='seller'",
        (session_id,),
    )
    conn.commit()
    cur.close()
    conn.close()


# ---------------------------------------------------------------------------
# customer_db read functions (unchanged — no broadcast needed)
# ---------------------------------------------------------------------------

def validate_session(session_id):
    if not session_id:
        return None
    conn = customer_db.get_connection()
    cur  = conn.cursor(dictionary=True)
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
        # Expired — delete directly on this replica only (best-effort; will
        # propagate on the next touch/logout from the client).
        _delete_seller_session_direct(session_id)
        return None
    return row["user_id"]


def _delete_seller_session_direct(session_id):
    """Local-only session cleanup (used for expiry; not replicated)."""
    conn = customer_db.get_connection()
    cur  = conn.cursor()
    cur.execute(
        "DELETE FROM sessions WHERE session_id=%s AND user_type='seller'",
        (session_id,),
    )
    conn.commit()
    cur.close()
    conn.close()


def touch_session(session_id):
    conn = customer_db.get_connection()
    cur  = conn.cursor()
    cur.execute(
        "UPDATE sessions SET last_active=NOW() WHERE session_id=%s AND user_type='seller'",
        (session_id,),
    )
    conn.commit()
    cur.close()
    conn.close()


def get_seller_rating(seller_id):
    conn = customer_db.get_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT thumbs_up, thumbs_down FROM sellers WHERE seller_id=%s",
        (seller_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


# ---------------------------------------------------------------------------
# product_db functions (unchanged — not part of customer DB replication)
# ---------------------------------------------------------------------------

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
    conn = product_db.get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("USE product_db")
    cur.execute(
        "INSERT INTO items (seller_id, item_name, category, condition_type, price, quantity) VALUES (%s, %s, %s, %s, %s, %s)",
        (seller_id, item_name, item_category, condition_type, salePrice, quantity),
    )
    item_id = cur.lastrowid
    for kw in keywords:
        cur.execute("INSERT INTO item_keywords (item_id, keyword) VALUES (%s, %s)", (item_id, kw))
    conn.commit()
    cur.close()
    conn.close()
    return True, {"item_id": item_id}


def display_items_for_sale(seller_id):
    conn = product_db.get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("USE product_db")
    cur.execute(
        "SELECT item_id, item_name, category, condition_type, price, quantity, thumbs_up, thumbs_down FROM items WHERE seller_id=%s",
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
    cur.execute("USE product_db")
    cur.execute(
        "SELECT quantity FROM items WHERE item_id=%s AND seller_id=%s",
        (item_id, seller_id),
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
        "UPDATE items SET quantity=%s WHERE item_id=%s AND seller_id=%s",
        (new_quantity, item_id, seller_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return True, f"Removed {quantity} units. New quantity: {new_quantity}"


def change_item_price(seller_id, item_id, price):
    conn = product_db.get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("USE product_db")
    cur.execute(
        "UPDATE items SET price=%s WHERE item_id=%s AND seller_id=%s",
        (price, item_id, seller_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return True, "UPDATED"


# ---------------------------------------------------------------------------
# Server entrypoint
# ---------------------------------------------------------------------------

def serve():
    host = SELLER_GRPC_CONFIG["host"]
    port = SELLER_GRPC_CONFIG["port"]

    broadcast_node.start()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    seller_pb2_grpc.add_SellerServiceServicer_to_server(SellerServicer(), server)
    server.add_insecure_port(f"{host}:{port}")
    server.start()
    print(f"Seller gRPC server started on {host}:{port}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
