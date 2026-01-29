import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.helper import send_msg, recv_msg
from server.buyer.config import BUYER_SERVER_CONFIG

SERVER_HOST = BUYER_SERVER_CONFIG["host"]
SERVER_PORT = BUYER_SERVER_CONFIG["port"]


class BuyerClient:
    def __init__(self, host=SERVER_HOST, port=SERVER_PORT):
        self.host = host
        self.port = port
        self.sock = None
        self.session_id = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        print("[BUYER][CLIENT] Connected to buyer server")

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
        print("\nBuyer CLI")
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
        elif parts[0] == "search":
            self.search(parts)
        elif parts[0] == "get_item":
            self.get_item(parts)
        elif parts[0] == "add_to_cart":
            self.add_to_cart(parts)
        elif parts[0] == "remove_from_cart":
            self.remove_from_cart(parts)
        elif parts[0] == "display_cart":
            self.display_cart()
        elif parts[0] == "clear_cart":
            self.clear_cart()
        elif parts[0] == "save_cart":
            self.save_cart()
        elif parts[0] == "rate_item":
            self.rate_item(parts)
        elif parts[0] == "get_seller_rating":
            self.get_seller_rating(parts)
        elif parts[0] == "get_purchases":
            self.get_purchases()
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

    def search(self, parts):
        if len(parts) < 2:
            print("Usage: search <category> [keywords...]")
            return
        category = int(parts[1])
        keywords = parts[2:]
        resp = self.send("search", {
            "category": category,
            "keywords": keywords,
        })
        print(resp)

    def get_item(self, parts):
        if len(parts) != 2:
            print("Usage: get_item <item_id>")
            return
        try:
            item_id = int(parts[1])
            if item_id <= 0:
                print("Error: Item ID must be a positive integer")
                return
            resp = self.send("get_item", {
                "item_id": item_id,
            })
            print(resp)
        except ValueError:
            print("Error: item_id must be a valid integer")

    def add_to_cart(self, parts):
        if len(parts) != 3:
            print("Usage: add_to_cart <item_id> <qty>")
            return
        try:
            item_id = int(parts[1])
            quantity = int(parts[2])
            if quantity <= 0:
                print("Error: Quantity must be a positive integer")
                return
            resp = self.send("add_to_cart", {
                "item_id": item_id,
                "quantity": quantity,
            })
            print(resp)
        except ValueError:
            print("Error: item_id and quantity must be valid integers")

    def remove_from_cart(self, parts):
        if len(parts) != 3:
            print("Usage: remove_from_cart <item_id> <qty>")
            return
        try:
            item_id = int(parts[1])
            quantity = int(parts[2])
            if quantity <= 0:
                print("Error: Quantity must be a positive integer")
                return
            resp = self.send("remove_from_cart", {
                "item_id": item_id,
                "quantity": quantity,
            })
            print(resp)
        except ValueError:
            print("Error: item_id and quantity must be valid integers")

    def display_cart(self):
        resp = self.send("display_cart")
        print(resp)

    def clear_cart(self):
        resp = self.send("clear_cart")
        print(resp)

    def save_cart(self):
        resp = self.send("save_cart")
        print(resp)

    def rate_item(self, parts):
        if len(parts) != 3 or parts[2] not in ("up", "down"):
            print("Usage: rate_item <item_id> up|down")
            return
        try:
            item_id = int(parts[1])
            if item_id <= 0:
                print("Error: Item ID must be a positive integer")
                return
            resp = self.send("provide_feedback", {
                "item_id": item_id,
                "feedback": parts[2],
            })
            print(resp)
        except ValueError:
            print("Error: item_id must be a valid integer")

    def get_seller_rating(self, parts):
        if len(parts) != 2:
            print("Usage: get_seller_rating <seller_id>")
            return
        try:
            seller_id = int(parts[1])
            if seller_id <= 0:
                print("Error: Seller ID must be a positive integer")
                return
            resp = self.send("get_seller_rating", {
                "seller_id": seller_id,
            })
            print(resp)
        except ValueError:
            print("Error: seller_id must be a valid integer")

    def get_purchases(self):
        resp = self.send("get_buyer_purchases")
        print(resp)

    def print_help(self):
        print("""
Commands:
1.     create_account <username> <password>
2.     login <username> <password>
3.     logout
4.     search <category> [keywords...]
5.     get_item <item_id>
6.     add_to_cart <item_id> <qty>
7.     remove_from_cart <item_id> <qty>
8.     display_cart
9.     clear_cart
10.    save_cart
11.    rate_item <item_id> up|down
12.    get_seller_rating <seller_id>
13.    get_purchases
14.    exit
        """)

def main():
    client = BuyerClient()
    client.connect()
    client.repl()

if __name__ == "__main__":
    main()
