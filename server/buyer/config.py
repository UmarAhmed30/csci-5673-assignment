import os
from dotenv import load_dotenv

load_dotenv()

BUYER_SERVER_CONFIG = {
    "host": os.getenv("BUYER_SERVER_HOST"),
    "port": int(os.getenv("BUYER_SERVER_PORT")),
    "session_timeout_secs": int(os.getenv("SESSION_TIMEOUT_SECS"))
}

# gRPC connection config (for REST server to connect to gRPC server)
BUYER_GRPC_CONFIG = {
    "host": os.getenv("BUYER_GRPC_HOST", "localhost"),
    "port": int(os.getenv("BUYER_GRPC_PORT", "50052")),
}
