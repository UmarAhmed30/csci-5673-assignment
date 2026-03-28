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
# db_layer/product/ must be on sys.path for `import product_pb2` to resolve.
sys.path.insert(0, str(Path(__file__).parent.parent / "product"))

from db_layer.seller.config import SELLER_SERVER_CONFIG, SELLER_GRPC_CONFIG
from db.client import CustomerDBClient
from broadcast.node import BroadcastNode
from db_layer.product.product_client import ResilientProductStub

import product_pb2

SESSION_TIMEOUT_SECS = SELLER_SERVER_CONFIG["session_timeout_secs"]

customer_db  = CustomerDBClient()
product_stub = ResilientProductStub()


# ---------------------------------------------------------------------------
# Broadcast node — started in serve(), used by SellerServicer write methods
# ---------------------------------------------------------------------------

def apply_operation(payload: dict):
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
    while broadcast_node.has_pending_deliveries():
        time.sleep(0.001)


# ---------------------------------------------------------------------------
# gRPC servicer
# ---------------------------------------------------------------------------

class SellerServicer(seller_pb2_grpc.SellerServiceServicer):

    # -- writes that touch customer_db → go through atomic broadcast ----------

    def CreateSeller(self, request, context):
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

    # -- product operations → via Raft-replicated product gRPC service -------

    def RegisterItem(self, request, context):
        # Pre-generate item_id so all product replicas insert the same row.
        new_item_id = random.randint(1, 2**31 - 1)

        # Validate inputs before sending to Raft (fail fast without burning consensus).
        if len(request.item_name) > 32:
            return seller_pb2.RegisterItemResponse(
                success=False, item_id=0, message="Item name must be 32 characters or less"
            )
        if request.item_category <= 0:
            return seller_pb2.RegisterItemResponse(
                success=False, item_id=0, message="Category must be a positive integer"
            )
        if request.quantity <= 0:
            return seller_pb2.RegisterItemResponse(
                success=False, item_id=0, message="Quantity must be a positive integer"
            )
        if request.sale_price <= 0:
            return seller_pb2.RegisterItemResponse(
                success=False, item_id=0, message="Price must be a positive number"
            )
        for kw in request.keywords:
            if len(kw) > 8:
                return seller_pb2.RegisterItemResponse(
                    success=False, item_id=0,
                    message="Keyword length must be <= 8 characters"
                )

        resp = product_stub.RegisterItem(
            product_pb2.RegisterItemRequest(
                item_id=new_item_id,
                seller_id=request.seller_id,
                item_name=request.item_name,
                category=request.item_category,
                condition_type=request.condition_type,
                price=request.sale_price,
                quantity=request.quantity,
                keywords=list(request.keywords),
            )
        )
        return seller_pb2.RegisterItemResponse(
            success=resp.success, item_id=resp.item_id, message=resp.message
        )

    def DisplayItems(self, request, context):
        resp = product_stub.DisplayItems(
            product_pb2.DisplayItemsRequest(seller_id=request.seller_id)
        )
        items = [
            seller_pb2.Item(
                item_id=i.item_id,
                item_name=i.item_name,
                category=i.category,
                condition_type=i.condition_type,
                price=i.price,
                quantity=i.quantity,
                thumbs_up=i.thumbs_up,
                thumbs_down=i.thumbs_down,
            )
            for i in resp.items
        ]
        return seller_pb2.DisplayItemsResponse(items=items)

    def UpdateUnitsForSale(self, request, context):
        if not isinstance(request.item_id, int) or request.item_id <= 0:
            return seller_pb2.UpdateUnitsForSaleResponse(
                success=False, message="Item ID must be a positive integer"
            )
        if not isinstance(request.quantity, int) or request.quantity <= 0:
            return seller_pb2.UpdateUnitsForSaleResponse(
                success=False, message="Quantity to remove must be a positive integer"
            )
        resp = product_stub.UpdateUnitsForSale(
            product_pb2.UpdateUnitsForSaleRequest(
                seller_id=request.seller_id,
                item_id=request.item_id,
                quantity=request.quantity,
            )
        )
        return seller_pb2.UpdateUnitsForSaleResponse(
            success=resp.success, message=resp.message
        )

    def ChangeItemPrice(self, request, context):
        resp = product_stub.ChangeItemPrice(
            product_pb2.ChangeItemPriceRequest(
                seller_id=request.seller_id,
                item_id=request.item_id,
                price=request.price,
            )
        )
        return seller_pb2.ChangeItemPriceResponse(
            success=resp.success, message=resp.message
        )


# ---------------------------------------------------------------------------
# customer_db write functions — replicated variants (called via apply_fn)
# ---------------------------------------------------------------------------

def create_seller_replicated(seller_id, username, password):
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
# customer_db read functions
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
        _delete_seller_session_direct(session_id)
        return None
    return row["user_id"]


def _delete_seller_session_direct(session_id):
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
