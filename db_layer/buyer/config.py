import os
from dotenv import load_dotenv

load_dotenv()

BUYER_SERVER_CONFIG = {
    "host": os.getenv("BUYER_SERVER_HOST"),
    "port": int(os.getenv("BUYER_SERVER_PORT")),
    "session_timeout_secs": int(os.getenv("SESSION_TIMEOUT_SECS"))
}

BUYER_GRPC_CONFIG = {
    "host": os.getenv("BUYER_GRPC_BIND_HOST", "0.0.0.0"),
    "port": int(os.getenv("BUYER_GRPC_PORT", "50052")),
}

# Broadcast group identity for this replica (0-4).
# Must match MY_NODE_ID in broadcast/config.py — both read from the same .env.
MY_NODE_ID = int(os.getenv("MY_NODE_ID", "0"))
