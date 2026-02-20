import sys
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.buyer.config import BUYER_SERVER_CONFIG

SERVER_HOST = BUYER_SERVER_CONFIG["host"]
SERVER_PORT = BUYER_SERVER_CONFIG["port"]


class BuyerClient:
    def __init__(self, host=SERVER_HOST, port=SERVER_PORT):
        self.host = host
        self.port = port
        self.session = None
        self.session_token = None
        self.base_url = f"http://{host}:{port}"

    def connect(self):
        self.session = requests.Session()
        print("[BUYER][CLIENT] Connected to buyer server")

    def close(self):
        if self.session:
            self.session.close()
            self.session = None

    def send(self, method, endpoint, json_data=None):
        url = f"{self.base_url}{endpoint}"
        headers = {}

        # Include session token in Authorization header if authenticated
        if self.session_token:
            headers["Authorization"] = f"Bearer {self.session_token}"

        try:
            if method == "GET":
                response = self.session.get(url, headers=headers, params=json_data)
            elif method == "POST":
                response = self.session.post(url, headers=headers, json=json_data)
            elif method == "PUT":
                response = self.session.put(url, headers=headers, json=json_data)
            elif method == "DELETE":
                response = self.session.delete(url, headers=headers, json=json_data)
            else:
                return {"status": "error", "message": f"Unsupported HTTP method: {method}"}

            try:
                data = response.json()
            except:
                data = {"message": response.text}

            if response.status_code in [200, 201]:
                return {"status": "ok", "data": data}
            elif response.status_code == 400:
                return {"status": "error", "message": data.get("detail", "Bad request")}
            elif response.status_code == 401:
                return {"status": "error", "message": data.get("detail", "Unauthorized")}
            elif response.status_code == 403:
                return {"status": "error", "message": data.get("detail", "Forbidden")}
            elif response.status_code == 404:
                return {"status": "error", "message": data.get("detail", "Not found")}
            elif response.status_code == 409:
                return {"status": "error", "message": data.get("detail", "Conflict")}
            elif response.status_code == 422:
                return {"status": "error", "message": data.get("detail", "Validation error")}
            elif response.status_code >= 500:
                return {"status": "error", "message": data.get("detail", "Server error")}
            else:
                return {"status": "error", "message": f"Unexpected status code: {response.status_code}"}

        except requests.exceptions.ConnectionError:
            return {"status": "error", "message": "Failed to connect to server"}
        except requests.exceptions.Timeout:
            return {"status": "error", "message": "Request timeout"}
        except Exception as e:
            return {"status": "error", "message": f"Request failed: {str(e)}"}

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
        elif parts[0] == "make_purchase":
            self.make_purchase(parts)
        else:
            print("Unknown command. Type `help`.")

    def create_account(self, parts):
        if len(parts) != 3:
            print("Usage: create_account <username> <password>")
            return
        resp = self.send("POST", "/api/buyers/register", {
            "username": parts[1],
            "password": parts[2],
        })
        if resp["status"] == "ok":
            print(f"[OK] {resp['data'].get('message', 'Account created')}")
        else:
            print(f"[ERROR] {resp.get('message', 'Unknown error')}")

    def login(self, parts):
        if len(parts) != 3:
            print("Usage: login <username> <password>")
            return
        if self.session_token:
            print("[ERROR] Already logged in. Please logout first.")
            return
        resp = self.send("POST", "/api/buyers/login", {
            "username": parts[1],
            "password": parts[2],
        })
        if resp["status"] == "ok":
            self.session_token = resp["data"].get("token")
            print("[OK] Logged in")
        else:
            print(f"[ERROR] {resp.get('message', 'Login failed')}")

    def logout(self):
        resp = self.send("POST", "/api/buyers/logout")
        self.session_token = None
        if resp.get("status") == "ok":
            print("[OK] Successfully logged out")
        else:
            print(f"[ERROR] {resp.get('message', 'Logout failed')}")

    def search(self, parts):
        if len(parts) < 2:
            print("Usage: search <category> [keywords...]")
            return
        category = parts[1]
        keywords = ",".join(parts[2:]) if len(parts) > 2 else None

        params = {"category": category}
        if keywords:
            params["keywords"] = keywords

        resp = self.send("GET", "/api/items/search", params)
        if resp["status"] == "ok":
            items = resp["data"].get("items", [])
            if items:
                print(f"[OK] Found {len(items)} items:")
                for item in items:
                    print(f"  - Item ID: {item.get('item_id')}, Name: {item.get('item_name')}, Price: ${item.get('price')}, Quantity: {item.get('quantity')}")
            else:
                print("[OK] No items found")
        else:
            print(f"[ERROR] {resp.get('message', 'Search failed')}")

    def get_item(self, parts):
        if len(parts) != 2:
            print("Usage: get_item <item_id>")
            return
        try:
            item_id = int(parts[1])
            if item_id <= 0:
                print("Error: Item ID must be a positive integer")
                return
            resp = self.send("GET", f"/api/items/{item_id}")
            if resp["status"] == "ok":
                item = resp["data"].get("item", {})
                print(f"[OK] Item details:")
                for key, value in item.items():
                    print(f"  {key}: {value}")
            else:
                print(f"[ERROR] {resp.get('message', 'Failed to get item')}")
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
            resp = self.send("POST", "/api/cart/items", {
                "item_id": item_id,
                "quantity": quantity,
            })
            if resp["status"] == "ok":
                print(f"[OK] {resp['data'].get('message', 'Item added to cart')}")
            else:
                print(f"[ERROR] {resp.get('message', 'Failed to add to cart')}")
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
            resp = self.send("DELETE", f"/api/cart/items/{item_id}", {
                "quantity": quantity,
            })
            if resp["status"] == "ok":
                print(f"[OK] {resp['data'].get('message', 'Item removed from cart')}")
            else:
                print(f"[ERROR] {resp.get('message', 'Failed to remove from cart')}")
        except ValueError:
            print("Error: item_id and quantity must be valid integers")

    def display_cart(self):
        resp = self.send("GET", "/api/cart")
        if resp["status"] == "ok":
            cart = resp["data"].get("cart", [])
            if cart:
                print(f"[OK] Cart contains {len(cart)} items:")
                for item in cart:
                    # Cart items only have item_id, quantity, and saved - no name or price
                    print(f"  - Item ID: {item.get('item_id')}, Quantity: {item.get('quantity')}, Saved: {item.get('saved')}")
            else:
                print("[OK] Cart is empty")
        else:
            print(f"[ERROR] {resp.get('message', 'Failed to display cart')}")

    def clear_cart(self):
        resp = self.send("DELETE", "/api/cart")
        if resp["status"] == "ok":
            print(f"[OK] {resp['data'].get('message', 'Cart cleared')}")
        else:
            print(f"[ERROR] {resp.get('message', 'Failed to clear cart')}")

    def save_cart(self):
        resp = self.send("POST", "/api/cart/save")
        if resp["status"] == "ok":
            print(f"[OK] {resp['data'].get('message', 'Cart saved successfully')}")
        else:
            print(f"[ERROR] {resp.get('message', 'Failed to save cart')}")

    def rate_item(self, parts):
        if len(parts) != 3 or parts[2] not in ("up", "down"):
            print("Usage: rate_item <item_id> up|down")
            return
        try:
            item_id = int(parts[1])
            if item_id <= 0:
                print("Error: Item ID must be a positive integer")
                return
            resp = self.send("POST", f"/api/items/{item_id}/feedback", {
                "feedback": parts[2],
            })
            if resp["status"] == "ok":
                print(f"[OK] {resp['data'].get('message', 'Feedback recorded')}")
            else:
                print(f"[ERROR] {resp.get('message', 'Failed to provide feedback')}")
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
            resp = self.send("GET", f"/api/sellers/{seller_id}/rating")
            if resp["status"] == "ok":
                rating = resp["data"].get("rating", {})
                print(f"[OK] Seller rating:")
                for key, value in rating.items():
                    print(f"  {key}: {value}")
            else:
                print(f"[ERROR] {resp.get('message', 'Failed to get seller rating')}")
        except ValueError:
            print("Error: seller_id must be a valid integer")

    def get_purchases(self):
        resp = self.send("GET", "/api/buyers/purchases")
        if resp["status"] == "ok":
            purchases = resp["data"].get("purchases", [])
            if purchases:
                print(f"[OK] Purchase history ({len(purchases)} items):")
                for purchase in purchases:
                    print(f"  - Item ID: {purchase.get('item_id')}, Quantity: {purchase.get('quantity')}, Timestamp: {purchase.get('timestamp')}")
            else:
                print("[OK] No purchase history")
        else:
            print(f"[ERROR] {resp.get('message', 'Failed to get purchases')}")

    def make_purchase(self, parts):
        if len(parts) != 5:
            print("Usage: make_purchase <card_holder_name> <card_number> <expiration_date> <security_code>")
            return
        resp = self.send("POST", "/api/purchases", {
            "card_holder_name": parts[1],
            "card_number": parts[2],
            "expiration_date": parts[3],
            "security_code": parts[4],
        })
        if resp["status"] == "ok":
            print(f"[OK] {resp['data'].get('message', 'Purchase completed successfully')}")
            items_purchased = resp['data'].get('items_purchased', 0)
            if items_purchased:
                print(f"  Items purchased: {items_purchased}")
        else:
            print(f"[ERROR] {resp.get('message', 'Purchase failed')}")

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
11.    make_purchase <card_holder_name> <card_number> <expiration_date> <security_code>
12.    rate_item <item_id> up|down
13.    get_seller_rating <seller_id>
14.    get_purchases
15.    exit
        """)

def main():
    client = BuyerClient()
    client.connect()
    client.repl()

if __name__ == "__main__":
    main()
