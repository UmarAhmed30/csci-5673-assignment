import os
from dotenv import load_dotenv

load_dotenv()

SELLER_SERVER_CONFIG = {
    "host": os.getenv("SELLER_SERVER_HOST"),
    "port": int(os.getenv("SELLER_SERVER_PORT")),
    "session_timeout_secs": int(os.getenv("SESSION_TIMEOUT_SECS"))
}

# Single gRPC endpoint (legacy / single-replica mode).
SELLER_GRPC_CONFIG = {
    "host": os.getenv("SELLER_GRPC_HOST", "localhost"),
    "port": int(os.getenv("SELLER_GRPC_PORT", "50051")),
}

# All 5 product-DB replica gRPC addresses (Raft group).
# The REST server tries each in round-robin order on failure.
SELLER_GRPC_REPLICAS = [
    {
        "host": os.getenv(f"SELLER_GRPC_REPLICA_{i}_HOST",
                          os.getenv("SELLER_GRPC_HOST", "localhost")),
        "port": int(os.getenv(f"SELLER_GRPC_REPLICA_{i}_PORT",
                              os.getenv("SELLER_GRPC_PORT", "50051"))),
    }
    for i in range(5)
]
