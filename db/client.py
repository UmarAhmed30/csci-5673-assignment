import sys
import mysql.connector
from pathlib import Path
from mysql.connector import pooling

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.config import CUSTOMER_DB_CONFIG, PRODUCT_DB_CONFIG

class CustomerDBClient:
    """Database client for Customer Database (buyers, sellers, sessions)"""
    def __init__(self):
        self.pool = pooling.MySQLConnectionPool(
            pool_name="customer_db_pool",
            pool_size=CUSTOMER_DB_CONFIG["pool_size"],
            host=CUSTOMER_DB_CONFIG["host"],
            port=CUSTOMER_DB_CONFIG["port"],
            user=CUSTOMER_DB_CONFIG["user"],
            password=CUSTOMER_DB_CONFIG["password"],
            database=CUSTOMER_DB_CONFIG["database"],
            autocommit=True
        )

    def get_connection(self):
        return self.pool.get_connection()

class ProductDBClient:
    """Database client for Product Database (items, cart, purchases)"""
    def __init__(self):
        self.pool = pooling.MySQLConnectionPool(
            pool_name="product_db_pool",
            pool_size=PRODUCT_DB_CONFIG["pool_size"],
            host=PRODUCT_DB_CONFIG["host"],
            port=PRODUCT_DB_CONFIG["port"],
            user=PRODUCT_DB_CONFIG["user"],
            password=PRODUCT_DB_CONFIG["password"],
            database=PRODUCT_DB_CONFIG["database"],
            autocommit=True
        )

    def get_connection(self):
        return self.pool.get_connection()

def main():
    # Test Customer DB
    print("Testing Customer Database...")
    customer_db = CustomerDBClient()
    conn = customer_db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM buyers;")
    result = cursor.fetchone()
    print("Customer DB connection successful! Query result:", result)
    cursor.close()
    conn.close()

    # Test Product DB
    print("\nTesting Product Database...")
    product_db = ProductDBClient()
    conn = product_db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM items;")
    result = cursor.fetchone()
    print("Product DB connection successful! Query result:", result)
    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()
