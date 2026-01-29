import sys
from pathlib import Path
import socket
import threading
import time

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.seller.helper import (
    create_seller,
    login_seller,
    logout_seller,
    validate_session,
    touch_session,
    get_seller_rating,
    register_item_for_sale,
    change_item_price,
    update_units_for_sale,
    display_items_for_sale
)


from server.seller.config import SELLER_SERVER_CONFIG
from utils.helper import recv_msg, send_msg, success, error

HOST = SELLER_SERVER_CONFIG["host"]
PORT = SELLER_SERVER_CONFIG["port"]


class SellerServer:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(128)
        print(f"[SERVER][SELLER] Listening on {self.host}:{self.port}")

    def start(self):
        while True:
            client_sock, addr = self.sock.accept()
            print(f"[SERVER][SELLER] Connection from {addr}")
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
            print("[SellerServer] Error:", e)
        finally:
            sock.close()

    def dispatch(self, req: dict):
        op = req.get("op")
        args = req.get("args", {})
        session_id = req.get("session_id")
        seller_id = validate_session(session_id) if session_id else None
        if op == "create_account":
            if seller_id:
                return error("Cannot create account while logged in. Please logout first.")
            return self.handle_create_account(args)
        if op == "login":
            if seller_id:
                return error("Already logged in. Please logout first.")
            return self.handle_login(args)
        if not seller_id:
            return error("Invalid or expired session")
        touch_session(session_id)
        if op == "logout":
            return self.handle_logout(session_id)
        if op == "get_seller_rating":
            return self.handle_get_seller_rating(seller_id)
        if op == "register_item_for_sale":
            return self.handle_register_item_for_sale(seller_id, args)
        if op == "display_items_for_sale":
            return self.handle_display_items_for_sale(seller_id)
        if op == "update_units_for_sale":
            return self.handle_update_units_for_sale(seller_id,args)
        if op == "change_item_price":
            return self.handle_change_item_price(seller_id,args)
        return error(f"Unknown operation: {op}")

    def handle_create_account(self, args):
        username = args.get("username")
        password = args.get("password")
        if not username or not password:
            return error("Missing username or password")
        result = create_seller(username, password)
        if isinstance(result, tuple):
            seller_id, msg = result
            if not seller_id:
                return error(msg)
            return success({"seller_id": seller_id})
        return success({"seller_id": result})

    def handle_login(self, args):
        username = args.get("username")
        password = args.get("password")
        session_id = login_seller(username, password)
        if not session_id:
            return error("Invalid credentials")
        return success({"session_id": session_id})

    def handle_logout(self, session_id):
        logout_seller(session_id)
        return success("Logged out")

    def handle_get_seller_rating(self, seller_id):
        rating = get_seller_rating(seller_id)
        return success(rating)

    def handle_register_item_for_sale(self, seller_id, args):
        item_name = args.get("item_name")
        category= args.get("category")
        condition_type = args.get("condition_type")
        price = args.get("price")
        quantity = args.get("quantity")
        keywords = args.get("keywords",[])
        ok, msg = register_item_for_sale(seller_id, item_name, category, condition_type, price, quantity, keywords)
        if not ok:
            return error(msg)
        return success(msg)

    def handle_update_units_for_sale(self, seller_id, args):
        category_id = args.get("category_id")
        item_number = args.get("item_number")
        quantity = args.get("quantity")
        ok, msg = update_units_for_sale(seller_id, category_id, item_number, quantity)
        if not ok:
            return error(msg)
        return success(msg)

    def handle_display_items_for_sale(self, seller_id):
        resp = display_items_for_sale(seller_id)
        return success(resp)

    def handle_change_item_price(self, seller_id, args):
        category_id = args.get("category_id")
        item_number = args.get("item_number")
        price = args.get("price")
        ok, msg = change_item_price(seller_id, category_id, item_number, price)
        if not ok:
            return error(msg)
        return success(msg)

def main():
    server = SellerServer()
    server.start()

if __name__ == "__main__":
    main()