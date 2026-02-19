import sys
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.seller.config import SELLER_SERVER_CONFIG

SERVER_HOST = SELLER_SERVER_CONFIG["host"]
SERVER_PORT = SELLER_SERVER_CONFIG["port"]


class SellerClient:
    def __init__(self, host=SERVER_HOST, port=SERVER_PORT):
        self.host = host
        self.port = port
        self.session = None
        self.session_token = None
        self.base_url = f"http://{host}:{port}"

    def connect(self):
        self.session = requests.Session()
        print("[SELLER][CLIENT] Connected to seller server")

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
        resp = self.send("POST", "/api/sellers/register", {
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
        resp = self.send("POST", "/api/sellers/login", {
            "username": parts[1],
            "password": parts[2],
        })
        if resp["status"] == "ok":
            self.session_token = resp["data"].get("token")
            print("[OK] Logged in")
        else:
            print(f"[ERROR] {resp.get('message', 'Login failed')}")

    def logout(self):
        resp = self.send("POST", "/api/sellers/logout")
        self.session_token = None
        if resp.get("status") == "ok":
            print("[OK] Successfully logged out")
        else:
            print(f"[ERROR] {resp.get('message', 'Logout failed')}")

    def get_seller_rating(self, parts):
        if len(parts) != 1:
            print("Usage: get_seller_rating")
            return
        resp = self.send("GET", "/api/sellers/rating")
        if resp["status"] == "ok":
            rating = resp["data"].get("rating", {})
            print(f"[OK] Seller rating:")
            for key, value in rating.items():
                print(f"  {key}: {value}")
        else:
            print(f"[ERROR] {resp.get('message', 'Failed to get seller rating')}")

    def register_item_for_sale(self, parts):
        if len(parts) < 7:
            print(
                "Usage: register_item_for_sale <item_name> <category> "
                "<condition_type> <price> <quantity> <keywords>"
            )
            return
        _, item_name, item_category, condition_type, sale_price, item_quantity = parts[:6]
        keywords = parts[6:]

        resp = self.send("POST", "/api/sellers/items", {
            "name": item_name,
            "category": int(item_category),
            "condition": condition_type,
            "price": float(sale_price),
            "quantity": int(item_quantity),
            "keywords": keywords
        })

        if resp["status"] == "ok":
            print(f"[OK] {resp['data'].get('message', 'Item registered successfully')}")
            if "item_id" in resp["data"]:
                print(f"  Item ID: {resp['data']['item_id']}")
        else:
            print(f"[ERROR] {resp.get('message', 'Failed to register item')}")

    def display_items_for_sale(self, parts):
        if len(parts) != 1:
            print("Usage: display_items_for_sale")
            return
        resp = self.send("GET", "/api/sellers/items")
        if resp["status"] == "ok":
            items = resp["data"].get("items", [])
            if items:
                print(f"[OK] You have {len(items)} items for sale:")
                for item in items:
                    print(f"  - Item ID: {item.get('item_id')}, Name: {item.get('name')}, Price: ${item.get('price')}, Quantity: {item.get('quantity')}")
            else:
                print("[OK] No items for sale")
        else:
            print(f"[ERROR] {resp.get('message', 'Failed to display items')}")

    def update_units_for_sale(self, parts):
        if len(parts) != 3:
            print(
                "Usage: update_units_for_sale <item_id> <quantity_to_remove>"
            )
            return
        try:
            item_id = int(parts[1])
            quantity = int(parts[2])
            if item_id <= 0:
                print("Error: Item ID must be a positive integer")
                return
            if quantity <= 0:
                print("Error: Quantity to remove must be a positive integer")
                return
            resp = self.send("PUT", f"/api/sellers/items/{item_id}/quantity", {
                "quantity": quantity
            })
            if resp["status"] == "ok":
                print(f"[OK] {resp['data'].get('message', 'Quantity updated successfully')}")
            else:
                print(f"[ERROR] {resp.get('message', 'Failed to update quantity')}")
        except ValueError:
            print("Error: item_id and quantity must be valid integers")

    def change_item_price(self, parts):
        if len(parts) != 3:
            print(
                "Usage: change_item_price <item_id> <itemPrice> "
            )
            return
        try:
            item_id = int(parts[1])
            price = float(parts[2])

            if item_id <= 0:
                print("Error: Item ID must be a positive integer")
                return
            if price <= 0:
                print("Error: Price must be a positive number")
                return

            resp = self.send("PUT", f"/api/sellers/items/{item_id}/price", {
                "price": price
            })

            if resp["status"] == "ok":
                print(f"[OK] {resp['data'].get('message', 'Price updated successfully')}")
            else:
                print(f"[ERROR] {resp.get('message', 'Failed to update price')}")
        except ValueError:
            print("Error: item_id must be a valid integer and price must be a valid number")

    def print_help(self):
        print("""
Commands:
1.     create_account <username> <password>
2.     login <username> <password>
3.     logout
4.     get_seller_rating
5.     display_items_for_sale
6.     register_item_for_sale <item_name> <category_id> <condition_type> <price> <quantity> <keywords>
7.     update_units_for_sale <item_id> <quantity_to_remove>
8.     change_item_price <item_id> <itemPrice>
9.     exit
        """)

def main():
    client = SellerClient()
    client.connect()
    client.repl()


if __name__ == "__main__":
    main()
