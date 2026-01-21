import sys
from pathlib import Path
import socket
import threading
import time

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.buyer.helper import (
    create_buyer,
    login_buyer,
    logout_session,
    validate_session,
    touch_session,
    search_items,
    get_item,
    add_to_cart,
    remove_from_cart,
    clear_cart,
    get_cart,
    save_cart,
    provide_item_feedback,
    get_seller_rating,
    get_buyer_purchases,
)

from server.buyer.config import BUYER_SERVER_CONFIG
from utils.helper import recv_msg, send_msg, success, error

HOST = BUYER_SERVER_CONFIG["host"]
PORT = BUYER_SERVER_CONFIG["port"]

class BuyerServer:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(128)
        print(f"[SERVER][BUYER] Listening on {self.host}:{self.port}")

    def start(self):
        while True:
            client_sock, addr = self.sock.accept()
            print(f"[SERVER][BUYER] Connection from {addr}")
            t = threading.Thread(
                target=self.handle_client,
                args=(client_sock,),
                daemon=True
            )
            t.start()

    def handle_client(self, sock):
        try:
            while True:
                req = recv_msg(sock)
                if not req:
                    break
                resp = self.dispatch(req)
                send_msg(sock, resp)
        except Exception as e:
            print("[BuyerServer] Error:", e)
        finally:
            sock.close()

    def dispatch(self, req: dict):
        op = req.get("op")
        args = req.get("args", {})
        session_id = req.get("session_id")
        if op == "create_account":
            return self.handle_create_account(args)
        if op == "login":
            return self.handle_login(args)
        buyer_id = validate_session(session_id)
        if not buyer_id:
            return error("Invalid or expired session")
        touch_session(session_id)
        if op == "logout":
            return self.handle_logout(session_id)
        if op == "search":
            return self.handle_search(args)
        if op == "get_item":
            return self.handle_get_item(args)
        if op == "add_to_cart":
            return self.handle_add_to_cart(buyer_id, args)
        if op == "remove_from_cart":
            return self.handle_remove_from_cart(buyer_id, args)
        if op == "clear_cart":
            return self.handle_clear_cart(buyer_id)
        if op == "display_cart":
            return self.handle_display_cart(buyer_id)
        if op == "save_cart":
            return self.handle_save_cart(buyer_id)
        if op == "provide_feedback":
            return self.handle_provide_feedback(args)
        if op == "get_seller_rating":
            return self.handle_get_seller_rating(args)
        if op == "get_buyer_purchases":
            return self.handle_get_buyer_purchases(buyer_id)
        return error(f"Unknown operation: {op}")

    def handle_create_account(self, args):
        username = args.get("username")
        password = args.get("password")
        if not username or not password:
            return error("Missing username or password")
        buyer_id = create_buyer(username, password)
        return success({"buyer_id": buyer_id})

    def handle_login(self, args):
        username = args.get("username")
        password = args.get("password")
        session_id = login_buyer(username, password)
        if not session_id:
            return error("Invalid credentials")
        return success({"session_id": session_id})

    def handle_logout(self, session_id):
        logout_session(session_id)
        return success("Logged out")

    def handle_search(self, args):
        category = args.get("category")
        keywords = args.get("keywords", [])
        results = search_items(category, keywords)
        return success(results)

    def handle_get_item(self, args):
        item_id = args.get("item_id")
        item = get_item(item_id)
        if not item:
            return error("Item not found")
        return success(item)

    def handle_add_to_cart(self, buyer_id, args):
        item_id = args.get("item_id")
        qty = args.get("quantity")
        ok, msg = add_to_cart(buyer_id, item_id, qty)
        if not ok:
            return error(msg)
        return success("Item added to cart")

    def handle_remove_from_cart(self, buyer_id, args):
        item_id = args.get("item_id")
        qty = args.get("quantity")
        ok, msg = remove_from_cart(buyer_id, item_id, qty)
        if not ok:
            return error(msg)
        return success("Item removed from cart")

    def handle_clear_cart(self, buyer_id):
        clear_cart(buyer_id)
        return success("Cart cleared")

    def handle_display_cart(self, buyer_id):
        cart = get_cart(buyer_id)
        return success(cart)

    def handle_save_cart(self, buyer_id):
        save_cart(buyer_id)
        return success("Cart saved")

    def handle_provide_feedback(self, args):
        item_id = args.get("item_id")
        feedback = args.get("feedback")
        provide_item_feedback(item_id, feedback)
        return success("Feedback recorded")

    def handle_get_seller_rating(self, args):
        seller_id = args.get("seller_id")
        rating = get_seller_rating(seller_id)
        return success(rating)

    def handle_get_buyer_purchases(self, buyer_id):
        purchases = get_buyer_purchases(buyer_id)
        return success(purchases)

def main():
    server = BuyerServer()
    server.start()

if __name__ == "__main__":
    main()
