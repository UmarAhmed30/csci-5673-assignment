import os
from dotenv import load_dotenv

load_dotenv()

CUSTOMER_DB_CONFIG = {
    "host": os.getenv("CUSTOMER_DB_HOST"),
    "port": int(os.getenv("CUSTOMER_DB_PORT")),
    "user": os.getenv("CUSTOMER_DB_USER"),
    "password": os.getenv("CUSTOMER_DB_PASSWORD"),
    "database": os.getenv("CUSTOMER_DB_NAME"),
    "pool_size": int(os.getenv("CUSTOMER_DB_POOL_SIZE", "200"))
}

PRODUCT_DB_CONFIG = {
    "host": os.getenv("PRODUCT_DB_HOST"),
    "port": int(os.getenv("PRODUCT_DB_PORT")),
    "user": os.getenv("PRODUCT_DB_USER"),
    "password": os.getenv("PRODUCT_DB_PASSWORD"),
    "database": os.getenv("PRODUCT_DB_NAME"),
    "pool_size": int(os.getenv("PRODUCT_DB_POOL_SIZE", "200"))
}
