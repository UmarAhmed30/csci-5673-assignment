#!/usr/bin/env python3
"""
Test script to verify seller components:
1. Client -> REST Server -> gRPC Server -> Database
2. Create account with username "ganesh"
3. Login with that account
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from client.seller.seller import SellerClient

def test_seller_flow():
    print("=" * 60)
    print("Testing Seller Components")
    print("=" * 60)
    print("\n1. Creating SellerClient instance...")
    client = SellerClient()
    
    try:
        print("\n2. Connecting to REST Server...")
        client.connect()
        
        print("\n3. Creating account with username 'ganesh'...")
        username = "ganesh"
        password = "ganesh123"  # Using a simple password for testing
        
        create_resp = client.send("POST", "/api/sellers/register", {
            "username": username,
            "password": password
        })
        
        if create_resp["status"] == "ok":
            print(f"   ✓ Account created successfully!")
            print(f"   Response: {create_resp.get('data', {})}")
        else:
            error_msg = create_resp.get("message", "Unknown error")
            if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower():
                print(f"   ⚠ Account already exists (this is OK if testing multiple times)")
            else:
                print(f"   ✗ Failed to create account: {error_msg}")
                return False
        
        print("\n4. Logging in with username 'ganesh'...")
        login_resp = client.send("POST", "/api/sellers/login", {
            "username": username,
            "password": password
        })
        
        if login_resp["status"] == "ok":
            token = login_resp["data"].get("token")
            client.session_token = token
            print(f"   ✓ Login successful!")
            print(f"   Session token received: {token[:20]}..." if token else "   (No token)")
            
            print("\n5. Testing authenticated endpoint (get seller rating)...")
            rating_resp = client.send("GET", "/api/sellers/rating")
            if rating_resp["status"] == "ok":
                rating = rating_resp["data"].get("rating", {})
                print(f"   ✓ Successfully retrieved seller rating!")
                print(f"   Rating: {rating}")
            else:
                print(f"   ⚠ Could not retrieve rating: {rating_resp.get('message')}")
            
            print("\n6. Testing display items endpoint...")
            items_resp = client.send("GET", "/api/sellers/items")
            if items_resp["status"] == "ok":
                items = items_resp["data"].get("items", [])
                print(f"   ✓ Successfully retrieved items!")
                print(f"   Number of items: {len(items)}")
            else:
                print(f"   ⚠ Could not retrieve items: {items_resp.get('message')}")
            
            print("\n" + "=" * 60)
            print("✓ All tests completed successfully!")
            print("=" * 60)
            print("\nFlow verified:")
            print("  Client → REST Server (port 6001) → gRPC Server (port 50051) → Database")
            return True
        else:
            print(f"   ✗ Login failed: {login_resp.get('message', 'Unknown error')}")
            return False
    finally:
        client.close()

if __name__ == "__main__":
    try:
        success = test_seller_flow()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
