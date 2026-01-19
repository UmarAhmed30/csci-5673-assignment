import sys
import mysql.connector
from pathlib import Path
from mysql.connector import pooling

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.config import DB_CONFIG

class DBClient:
    def __init__(self):
        self.pool = pooling.MySQLConnectionPool(
            pool_name="marketplace_pool",
            pool_size=DB_CONFIG["pool_size"],
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
            autocommit=True
        )

    def get_connection(self):
        return self.pool.get_connection()

def main():
    db_client = DBClient()
    conn = db_client.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * from buyers;")
    result = cursor.fetchone()
    print("Database connection successful! Query result:", result)
    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()
