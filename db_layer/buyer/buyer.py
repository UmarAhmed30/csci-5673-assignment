import grpc
from concurrent import futures
import buyer_pb2
import buyer_pb2_grpc
import sys
import random
from pathlib import Path
import uuid
import time

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
# db_layer/product/ must be on sys.path for `import product_pb2` to resolve.
sys.path.insert(0, str(Path(__file__).parent.parent / "product"))

from db_layer.buyer.config import BUYER_SERVER_CONFIG, BUYER_GRPC_CONFIG
from db.client import CustomerDBClient
from broadcast.node import BroadcastNode
from db_layer.product.product_client import ResilientProductStub

import product_pb2

SESSION_TIMEOUT_SECS = BUYER_SERVER_CONFIG["session_timeout_secs"]

customer_db  = CustomerDBClient()
product_stub = ResilientProductStub()


# ---------------------------------------------------------------------------
# Broadcast node — started in serve(), used by BuyerServicer write methods
# ---------------------------------------------------------------------------

def apply_operation(payload: dict):
    op   = payload["op"]
    args = payload["args"]

    if op == "create_buyer":
        return create_buyer_replicated(
            args["buyer_id"], args["username"], args["password"]
        )
    if op == "login_buyer":
        return login_buyer_replicated(
            args["username"], args["password"], args["session_id"]
        )
    if op == "logout_session":
        return delete_session_replicated(args["session_id"])
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

class BuyerServicer(buyer_pb2_grpc.BuyerServiceServicer):

    # -- writes that touch customer_db → go through atomic broadcast ----------

    def CreateBuyer(self, request, context):
        new_buyer_id = random.randint(1, 2**31 - 1)
        result = broadcast_node.broadcast_request({
            "op": "create_buyer",
            "args": {
                "buyer_id": new_buyer_id,
                "username": request.username,
                "password": request.password,
            },
        })
        buyer_id, message = result
        return buyer_pb2.CreateBuyerResponse(
            buyer_id=buyer_id if buyer_id is not None else 0,
            message=message,
        )

    def LoginBuyer(self, request, context):
        session_id = str(uuid.uuid4())
        result = broadcast_node.broadcast_request({
            "op": "login_buyer",
            "args": {
                "username":   request.username,
                "password":   request.password,
                "session_id": session_id,
            },
        })
        return buyer_pb2.LoginBuyerResponse(
            session_id=result if result is not None else ""
        )

    def LogoutBuyer(self, request, context):
        buyer_id = broadcast_node.broadcast_request({
            "op": "logout_session",
            "args": {"session_id": request.session_id},
        })
        if buyer_id:
            product_stub.ClearUnsavedCart(
                product_pb2.ClearUnsavedCartRequest(buyer_id=buyer_id)
            )
        return buyer_pb2.LogoutBuyerResponse()

    def TouchSession(self, request, context):
        broadcast_node.broadcast_request({
            "op": "touch_session",
            "args": {"session_id": request.session_id},
        })
        return buyer_pb2.TouchSessionResponse()

    # -- reads from customer_db → wait for consistency first -----------------

    def ValidateSession(self, request, context):
        _wait_for_read_consistency()
        user_id = validate_session(request.session_id)
        return buyer_pb2.ValidateSessionResponse(
            user_id=user_id if user_id is not None else 0
        )

    def GetSellerRating(self, request, context):
        _wait_for_read_consistency()
        row = get_seller_rating(request.seller_id)
        if not row:
            return buyer_pb2.GetSellerRatingResponse(
                success=False, message="Seller not found",
            )
        return buyer_pb2.GetSellerRatingResponse(
            success=True,
            thumbs_up=row["thumbs_up"],
            thumbs_down=row["thumbs_down"],
            message="OK",
        )

    # -- product operations → via Raft-replicated product gRPC service -------

    def SearchItems(self, request, context):
        resp = product_stub.SearchItems(
            product_pb2.SearchItemsRequest(
                category=request.category,
                keywords=list(request.keywords),
            )
        )
        items = [
            buyer_pb2.Item(
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
        return buyer_pb2.SearchItemsResponse(items=items)

    def GetItem(self, request, context):
        resp = product_stub.GetItem(
            product_pb2.GetItemRequest(item_id=request.item_id)
        )
        if not resp.success:
            return buyer_pb2.GetItemResponse(success=False, message=resp.message)
        return buyer_pb2.GetItemResponse(
            success=True,
            item=buyer_pb2.Item(
                item_id=resp.item.item_id,
                item_name=resp.item.item_name,
                category=resp.item.category,
                condition_type=resp.item.condition_type,
                price=resp.item.price,
                quantity=resp.item.quantity,
                thumbs_up=resp.item.thumbs_up,
                thumbs_down=resp.item.thumbs_down,
            ),
            message="OK",
        )

    def AddToCart(self, request, context):
        resp = product_stub.AddToCart(
            product_pb2.AddToCartRequest(
                buyer_id=request.buyer_id,
                item_id=request.item_id,
                quantity=request.quantity,
            )
        )
        return buyer_pb2.AddToCartResponse(success=resp.success, message=resp.message)

    def RemoveFromCart(self, request, context):
        resp = product_stub.RemoveFromCart(
            product_pb2.RemoveFromCartRequest(
                buyer_id=request.buyer_id,
                item_id=request.item_id,
                quantity=request.quantity,
            )
        )
        return buyer_pb2.RemoveFromCartResponse(success=resp.success, message=resp.message)

    def GetCart(self, request, context):
        resp = product_stub.GetCart(
            product_pb2.GetCartRequest(buyer_id=request.buyer_id)
        )
        cart_items = [
            buyer_pb2.CartItem(
                item_id=i.item_id,
                quantity=i.quantity,
                saved=i.saved,
            )
            for i in resp.items
        ]
        return buyer_pb2.GetCartResponse(items=cart_items)

    def ClearCart(self, request, context):
        product_stub.ClearCart(
            product_pb2.ClearCartRequest(buyer_id=request.buyer_id)
        )
        return buyer_pb2.ClearCartResponse()

    def SaveCart(self, request, context):
        resp = product_stub.SaveCart(
            product_pb2.SaveCartRequest(buyer_id=request.buyer_id)
        )
        return buyer_pb2.SaveCartResponse(success=resp.success, message=resp.message)

    def ProvideItemFeedback(self, request, context):
        resp = product_stub.ProvideItemFeedback(
            product_pb2.ProvideItemFeedbackRequest(
                item_id=request.item_id,
                feedback=request.feedback,
            )
        )
        return buyer_pb2.ProvideItemFeedbackResponse(
            success=resp.success, message=resp.message
        )

    def GetBuyerPurchases(self, request, context):
        resp = product_stub.GetBuyerPurchases(
            product_pb2.GetBuyerPurchasesRequest(buyer_id=request.buyer_id)
        )
        purchases = [
            buyer_pb2.Purchase(
                item_id=p.item_id,
                timestamp=p.timestamp,
                quantity=p.quantity,
            )
            for p in resp.purchases
        ]
        return buyer_pb2.GetBuyerPurchasesResponse(purchases=purchases)

    def MakePurchase(self, request, context):
        cart_items_pb = [
            product_pb2.WriteCartItem(
                item_id=item.item_id,
                quantity=item.quantity,
            )
            for item in request.cart_items
        ]
        resp = product_stub.MakePurchase(
            product_pb2.MakePurchaseRequest(
                buyer_id=request.buyer_id,
                cart_items=cart_items_pb,
            )
        )
        return buyer_pb2.MakePurchaseResponse(
            success=resp.success,
            message=resp.message,
            items_purchased=resp.items_purchased,
        )


# ---------------------------------------------------------------------------
# customer_db write functions — replicated variants (called via apply_fn)
# ---------------------------------------------------------------------------

def create_buyer_replicated(buyer_id, username, password):
    if len(username) > 32:
        return None, "Username must be 32 characters or less"
    conn = customer_db.get_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO buyers (buyer_id, buyer_name, password) VALUES (%s, %s, %s)",
            (buyer_id, username, password),
        )
        conn.commit()
        cur.close()
        conn.close()
        return buyer_id, "OK"
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return None, str(e)


def login_buyer_replicated(username, password, session_id):
    conn = customer_db.get_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT buyer_id FROM buyers WHERE buyer_name=%s AND password=%s",
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
            "VALUES (%s, %s, 'buyer')",
            (session_id, row["buyer_id"]),
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


def delete_session_replicated(session_id):
    conn = customer_db.get_connection()
    cur  = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT user_id FROM sessions WHERE session_id=%s AND user_type='buyer'",
        (session_id,),
    )
    row      = cur.fetchone()
    buyer_id = row["user_id"] if row else None
    cur.execute("DELETE FROM sessions WHERE session_id=%s", (session_id,))
    conn.commit()
    cur.close()
    conn.close()
    return buyer_id


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
        _delete_session_direct(session_id)
        return None
    return row["user_id"]


def _delete_session_direct(session_id):
    conn = customer_db.get_connection()
    cur  = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE session_id=%s", (session_id,))
    conn.commit()
    cur.close()
    conn.close()


def touch_session(session_id):
    conn = customer_db.get_connection()
    cur  = conn.cursor()
    cur.execute(
        "UPDATE sessions SET last_active=NOW() WHERE session_id=%s",
        (session_id,),
    )
    conn.commit()
    cur.close()
    conn.close()


def get_seller_rating(seller_id):
    if not isinstance(seller_id, int) or seller_id <= 0:
        return None
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
    host = BUYER_GRPC_CONFIG["host"]
    port = BUYER_GRPC_CONFIG["port"]

    broadcast_node.start()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    buyer_pb2_grpc.add_BuyerServiceServicer_to_server(BuyerServicer(), server)
    server.add_insecure_port(f"{host}:{port}")
    server.start()
    print(f"Buyer gRPC server started on {host}:{port}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
