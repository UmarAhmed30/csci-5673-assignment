import socket
import sys
from pathlib import Path
import time
import threading

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.helper import send_msg, recv_msg
from server.seller.config import SELLER_SERVER_CONFIG

SERVER_HOST = SELLER_SERVER_CONFIG["host"]
SERVER_PORT = SELLER_SERVER_CONFIG["port"]


class SellerClient:
    def __init__(self, host=SERVER_HOST, port=SERVER_PORT):
        self.host = host
        self.port = port
        self.sock = None
        self.session_id = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        print("[SELLER][CLIENT] Connected to seller server")

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def send(self, op, args=None):
        msg = {"op": op}
        if args:
            msg["args"] = args
        if self.session_id:
            msg["session_id"] = self.session_id
        send_msg(self.sock, msg)
        resp = recv_msg(self.sock)
        return resp

    def repl(self):
        print("\nSeller CLI")
        print("Type `help` to see commands\n")
        while True:
            try:
                cmd = input("> ").strip()
                if not cmd:
                    continue
                if cmd == "exit":
                    print("Bye!")
                    break
                if cmd == "help":
                    self.print_help()
                    continue
                self.handle_command(cmd)
            except KeyboardInterrupt:
                print("\nInterrupted.")
                break
        self.close()

    def handle_command(self, cmd):
        parts = cmd.split()
        if parts[0] == "create_account":
            self.create_account(parts)
        elif parts[0] == "login":
            self.login(parts)
        elif parts[0] == "logout":
            self.logout()
        elif parts[0] == "get_seller_rating":
            self.get_seller_rating(parts)
        elif parts[0] == "display_items_for_sale":
            self.display_items_for_sale(parts)
        elif parts[0] == "register_item_for_sale":
            self.register_item_for_sale(parts)
        elif parts[0] == "update_units_for_sale":
            self.update_units_for_sale(parts)
        elif parts[0] == "change_item_price":
            self.change_item_price(parts)
        else:
            print("Unknown command. Type `help`.")

    def create_account(self, parts):
        if len(parts) != 3:
            print("Usage: create_account <username> <password>")
            return
        resp = self.send("create_account", {
            "username": parts[1],
            "password": parts[2],
        })
        print(resp)

    def login(self, parts):
        if len(parts) != 3:
            print("Usage: login <username> <password>")
            return
        resp = self.send("login", {
            "username": parts[1],
            "password": parts[2],
        })
        if resp["status"] == "ok":
            self.session_id = resp["data"]["session_id"]
            print("[OK] Logged in")
        else:
            print(resp)

    def logout(self):
        resp = self.send("logout")
        self.session_id = None
        if resp.get("status") == "ok":
            print("[OK] Successfully logged out")
        else:
            print(resp)

    def get_seller_rating(self, parts):
        if len(parts) != 1:
            print("Usage: get_seller_rating")
            return
        resp = self.send("get_seller_rating")
        print(resp)

    def register_item_for_sale(self, parts):
        if len(parts) < 7:
            print(
                "Usage: register_item_for_sale <item_name> <category> "
                "<condition_type> <price> <quantity> <keywords>"
            )
            return
        _, item_name, item_category, condition_type, sale_price, item_quantity = parts[:6]
        keywords = parts[6:]

        resp = self.send("register_item_for_sale", {
            "item_name": item_name,
            "category": item_category,
            "condition_type": condition_type,
            "price": float(sale_price),
            "quantity": int(item_quantity),
            "keywords": keywords
        })

        print(resp)

    def display_items_for_sale(self, parts):
        if len(parts) != 1:
            print("Usage: display_items_for_sale")
            return
        resp = self.send("display_items_for_sale")
        print(resp)

    def update_units_for_sale(self, parts):
        if len(parts) != 4:
            print(
                "Usage: update_units_for_sale <category_id> <item_number> <quantity_to_remove>"
            )
            return
        try:
            category_id = int(parts[1])
            item_number = int(parts[2])
            quantity = int(parts[3])
            if category_id <= 0 or item_number <= 0:
                print("Error: Category ID and Item number must be positive integers")
                return
            if quantity <= 0:
                print("Error: Quantity to remove must be a positive integer")
                return
            resp = self.send("update_units_for_sale", {
                "category_id": category_id,
                "item_number": item_number,
                "quantity": int(quantity)
            })
            print(resp)
        except ValueError:
            print("Error: category_id, item_number, and quantity must be valid integers")

    def change_item_price(self, parts):
        if len(parts) != 4:
            print(
                "Usage: change_item_price <category_id> <item_number> <itemPrice> "
            )
            return
        _, category_id, item_number, price = parts

        resp = self.send("change_item_price", {
            "category_id": category_id,
            "item_number": item_number,
            "price": float(price)
        })

        print(resp)

    def print_help(self):
        print("""
Commands:
1.     create_account <username> <password>
2.     login <username> <password>
3.     logout
4.     get_seller_rating
5.     display_items_for_sale
6.     register_item_for_sale <item_name> <category> <condition_type> <price> <quantity> <keywords>
7.     update_units_for_sale <category_id> <item_number> <quantity_to_remove>
8.     change_item_price <category_id> <item_number> <itemPrice>
9.     exit
                """)

def main():
    client = SellerClient()
    client.connect()
    client.repl()


if __name__ == "__main__":
    main()
