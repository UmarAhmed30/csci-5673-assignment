"""
db_layer/product/product_server.py

gRPC server for the Raft-replicated product database service.

Write RPCs delegate to ProductRaftNode using pysyncobj's callback pattern so
the calling thread blocks until Raft consensus is reached and the actual result
is available.  Read RPCs bypass Raft and query local MySQL directly.

Error handling:
  - err argument in callback is non-None when pysyncobj reports FAIL (not
    leader / cluster unavailable) or any other non-success status.
  - Both the err check AND any NotLeaderException must surface as
    gRPC UNAVAILABLE so ResilientProductStub can apply its backoff retry.
"""

import grpc
import sys
import threading
import random
import time
from concurrent import futures
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import product_pb2
import product_pb2_grpc

from db_layer.product.config import PRODUCT_GRPC_CONFIG
from db_layer.product.product_node import make_node

raft_node = make_node()


def _replicated_call(fn, *args, timeout: float = 10.0):
    """
    Call a @replicated method and block until the callback fires.

    Returns (result, err).  err is non-None when pysyncobj signals failure
    (FAIL status, not-leader, etc.) — the gRPC servicer must check this and
    return UNAVAILABLE so ResilientProductStub can retry.
    """
    event = threading.Event()
    result_box = [None]

    def cb(res, err):
        result_box[0] = (res, err)
        event.set()

    try:
        fn(*args, callback=cb)
    except Exception as exc:
        return None, exc

    fired = event.wait(timeout=timeout)
    if not fired:
        return None, TimeoutError("Raft consensus timed out")

    return result_box[0]


def _unavailable(context, detail: str):
    context.set_code(grpc.StatusCode.UNAVAILABLE)
    context.set_details(detail)


class ProductServicer(product_pb2_grpc.ProductServiceServicer):

    # -----------------------------------------------------------------------
    # Read RPCs — local MySQL, no Raft
    # -----------------------------------------------------------------------

    def SearchItems(self, request, context):
        rows = raft_node.search_items(request.category, list(request.keywords))
        items = [
            product_pb2.Item(
                item_id=r["item_id"],
                seller_id=r["seller_id"],
                item_name=r["item_name"],
                category=r["category"],
                condition_type=r["condition_type"],
                price=r["price"],
                quantity=r["quantity"],
                thumbs_up=r["thumbs_up"],
                thumbs_down=r["thumbs_down"],
            )
            for r in rows
        ]
        return product_pb2.SearchItemsResponse(items=items)

    def GetItem(self, request, context):
        row = raft_node.get_item(request.item_id)
        if not row:
            return product_pb2.GetItemResponse(success=False, message="Item not found")
        return product_pb2.GetItemResponse(
            success=True,
            item=product_pb2.Item(
                item_id=row["item_id"],
                seller_id=row["seller_id"],
                item_name=row["item_name"],
                category=row["category"],
                condition_type=row["condition_type"],
                price=row["price"],
                quantity=row["quantity"],
                thumbs_up=row["thumbs_up"],
                thumbs_down=row["thumbs_down"],
            ),
            message="OK",
        )

    def GetCart(self, request, context):
        rows = raft_node.get_cart(request.buyer_id)
        items = [
            product_pb2.CartItem(
                item_id=r["item_id"],
                quantity=r["quantity"],
                saved=bool(r["saved"]),
            )
            for r in rows
        ]
        return product_pb2.GetCartResponse(items=items)

    def GetBuyerPurchases(self, request, context):
        rows = raft_node.get_buyer_purchases(request.buyer_id)
        purchases = [
            product_pb2.Purchase(
                item_id=r["item_id"],
                quantity=r["quantity"],
                timestamp=str(r["timestamp"]),
            )
            for r in rows
        ]
        return product_pb2.GetBuyerPurchasesResponse(purchases=purchases)

    def DisplayItems(self, request, context):
        rows = raft_node.display_items(request.seller_id)
        items = [
            product_pb2.Item(
                item_id=r["item_id"],
                seller_id=r["seller_id"],
                item_name=r["item_name"],
                category=r["category"],
                condition_type=r["condition_type"],
                price=r["price"],
                quantity=r["quantity"],
                thumbs_up=r["thumbs_up"],
                thumbs_down=r["thumbs_down"],
            )
            for r in rows
        ]
        return product_pb2.DisplayItemsResponse(items=items)

    # -----------------------------------------------------------------------
    # Write RPCs — replicated via Raft, callback pattern
    # -----------------------------------------------------------------------

    def AddToCart(self, request, context):
        res, err = _replicated_call(
            raft_node.add_to_cart,
            request.buyer_id, request.item_id, request.quantity,
        )
        if err:
            _unavailable(context, f"Raft write failed: {err}")
            return product_pb2.AddToCartResponse()
        success, message = res
        return product_pb2.AddToCartResponse(success=success, message=message)

    def RemoveFromCart(self, request, context):
        res, err = _replicated_call(
            raft_node.remove_from_cart,
            request.buyer_id, request.item_id, request.quantity,
        )
        if err:
            _unavailable(context, f"Raft write failed: {err}")
            return product_pb2.RemoveFromCartResponse()
        success, message = res
        return product_pb2.RemoveFromCartResponse(success=success, message=message)

    def ClearCart(self, request, context):
        res, err = _replicated_call(raft_node.clear_cart, request.buyer_id)
        if err:
            _unavailable(context, f"Raft write failed: {err}")
        return product_pb2.ClearCartResponse()

    def ClearUnsavedCart(self, request, context):
        res, err = _replicated_call(raft_node.clear_unsaved_cart, request.buyer_id)
        if err:
            _unavailable(context, f"Raft write failed: {err}")
        return product_pb2.ClearUnsavedCartResponse()

    def SaveCart(self, request, context):
        res, err = _replicated_call(raft_node.save_cart, request.buyer_id)
        if err:
            _unavailable(context, f"Raft write failed: {err}")
            return product_pb2.SaveCartResponse()
        success, message = res
        return product_pb2.SaveCartResponse(success=success, message=message)

    def ProvideItemFeedback(self, request, context):
        res, err = _replicated_call(
            raft_node.provide_item_feedback, request.item_id, request.feedback
        )
        if err:
            _unavailable(context, f"Raft write failed: {err}")
            return product_pb2.ProvideItemFeedbackResponse()
        success, message = res
        return product_pb2.ProvideItemFeedbackResponse(success=success, message=message)

    def MakePurchase(self, request, context):
        cart_items = [
            {"item_id": item.item_id, "quantity": item.quantity}
            for item in request.cart_items
        ]
        res, err = _replicated_call(
            raft_node.make_purchase, request.buyer_id, cart_items
        )
        if err:
            _unavailable(context, f"Raft write failed: {err}")
            return product_pb2.MakePurchaseResponse()
        success, message = res
        return product_pb2.MakePurchaseResponse(
            success=success,
            message=message,
            items_purchased=len(cart_items) if success else 0,
        )

    def RegisterItem(self, request, context):
        # item_id is pre-generated by the caller (buyer/seller gRPC layer)
        # and passed here for deterministic replication across all nodes.
        res, err = _replicated_call(
            raft_node.register_item,
            request.item_id,
            request.seller_id,
            request.item_name,
            request.category,
            request.condition_type,
            request.price,
            request.quantity,
            list(request.keywords),
        )
        if err:
            _unavailable(context, f"Raft write failed: {err}")
            return product_pb2.RegisterItemResponse()
        success, item_id, message = res
        return product_pb2.RegisterItemResponse(
            success=success, item_id=item_id, message=message
        )

    def UpdateUnitsForSale(self, request, context):
        res, err = _replicated_call(
            raft_node.update_units_for_sale,
            request.seller_id, request.item_id, request.quantity,
        )
        if err:
            _unavailable(context, f"Raft write failed: {err}")
            return product_pb2.UpdateUnitsForSaleResponse()
        success, message = res
        return product_pb2.UpdateUnitsForSaleResponse(success=success, message=message)

    def ChangeItemPrice(self, request, context):
        res, err = _replicated_call(
            raft_node.change_item_price,
            request.seller_id, request.item_id, request.price,
        )
        if err:
            _unavailable(context, f"Raft write failed: {err}")
            return product_pb2.ChangeItemPriceResponse()
        success, message = res
        return product_pb2.ChangeItemPriceResponse(success=success, message=message)


def _status_watcher(node, self_addr):
    last_leader = None
    last_ready = False
    while True:
        try:
            ready = node.isReady()
            leader = node._getLeader()
            if ready != last_ready or leader != last_leader:
                if str(leader) == str(self_addr):
                    role = "LEADER"
                else:
                    role = f"follower (leader={leader})"
                print(f"[Raft] ready={ready}  role={role}", flush=True)
                last_ready, last_leader = ready, leader
        except Exception:
            pass
        time.sleep(1.0)


def serve():
    host = PRODUCT_GRPC_CONFIG["host"]
    port = PRODUCT_GRPC_CONFIG["port"]

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    product_pb2_grpc.add_ProductServiceServicer_to_server(ProductServicer(), server)
    server.add_insecure_port(f"{host}:{port}")
    server.start()
    from db_layer.product.config import RAFT_SELF_ADDR
    print(f"Product gRPC server started on {host}:{port} (Raft addr: {RAFT_SELF_ADDR})", flush=True)
    t = threading.Thread(target=_status_watcher, args=(raft_node, RAFT_SELF_ADDR), daemon=True)
    t.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
