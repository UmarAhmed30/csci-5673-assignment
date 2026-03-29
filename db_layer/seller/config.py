import os
from dotenv import load_dotenv

load_dotenv()

SELLER_SERVER_CONFIG = {
    "host": os.getenv("SELLER_SERVER_HOST", "0.0.0.0"),
    "port": int(os.getenv("SELLER_SERVER_PORT", "0")),
    "session_timeout_secs": int(os.getenv("SESSION_TIMEOUT_SECS", "300")),
}

SELLER_GRPC_CONFIG = {
    "host": os.getenv("SELLER_GRPC_BIND_HOST", "0.0.0.0"),
    "port": int(os.getenv("SELLER_GRPC_PORT", "50051")),
}

MY_NODE_ID = int(os.getenv("MY_NODE_ID", "0"))
