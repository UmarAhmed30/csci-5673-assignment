import os
from dotenv import load_dotenv

load_dotenv()

# gRPC server bind config (used by product_server.py)
PRODUCT_GRPC_CONFIG = {
    "host": os.getenv("PRODUCT_GRPC_BIND_HOST", "0.0.0.0"),
    "port": int(os.getenv("PRODUCT_GRPC_PORT", "50070")),
}

# Raft node config (used by product_node.py)
MY_NODE_ID = int(os.getenv("PRODUCT_NODE_ID", "0"))

RAFT_NODES = [
    f"{os.getenv(f'RAFT_NODE_{i}_HOST', '127.0.0.1')}:{os.getenv(f'RAFT_NODE_{i}_PORT', str(7100 + i))}"
    for i in range(5)
]

RAFT_SELF_ADDR = RAFT_NODES[MY_NODE_ID]
RAFT_PARTNER_ADDRS = [addr for i, addr in enumerate(RAFT_NODES) if i != MY_NODE_ID]

# Product DB credentials for this replica's local MySQL
PRODUCT_DB_CONFIG = {
    "host":     os.getenv("PRODUCT_DB_HOST", "localhost"),
    "port":     int(os.getenv("PRODUCT_DB_PORT", "3306")),
    "user":     os.getenv("PRODUCT_DB_USER", "root"),
    "password": os.getenv("PRODUCT_DB_PASSWORD", "root"),
    "database": os.getenv("PRODUCT_DB_NAME", "product_db"),
}

# All 5 product gRPC replica addresses (used by ResilientProductStub)
PRODUCT_GRPC_REPLICAS = [
    {
        "host": os.getenv(f"PRODUCT_GRPC_REPLICA_{i}_HOST", "localhost"),
        "port": int(os.getenv(f"PRODUCT_GRPC_REPLICA_{i}_PORT", str(50070 + i))),
    }
    for i in range(5)
]
