import os
from dotenv import load_dotenv

load_dotenv()

BUYER_SERVER_CONFIG = {
    "host": os.getenv("BUYER_SERVER_HOST"),
    "port": int(os.getenv("BUYER_SERVER_PORT")),
    "session_timeout_secs": int(os.getenv("SESSION_TIMEOUT_SECS"))
}

# Single gRPC endpoint (legacy / single-replica mode).
BUYER_GRPC_CONFIG = {
    "host": os.getenv("BUYER_GRPC_HOST", "localhost"),
    "port": int(os.getenv("BUYER_GRPC_PORT", "50052")),
}

FINANCIAL_SOAP_URL = (
    f"http://{os.getenv('FINANCIAL_SERVICE_HOST', 'localhost')}"
    f":{os.getenv('FINANCIAL_SERVICE_PORT', '8002')}/?wsdl"
)

# All 5 customer-DB replica gRPC addresses.
# The REST server tries each in round-robin order on failure.
# Defaults keep localhost behaviour so existing .env files still work.
BUYER_GRPC_REPLICAS = [
    {
        "host": os.getenv(f"BUYER_GRPC_REPLICA_{i}_HOST",
                          os.getenv("BUYER_GRPC_HOST", "localhost")),
        "port": int(os.getenv(f"BUYER_GRPC_REPLICA_{i}_PORT",
                              os.getenv("BUYER_GRPC_PORT", "50052"))),
    }
    for i in range(5)
]
