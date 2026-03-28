"""
db_layer/product/product_client.py

ResilientProductStub — gRPC client for the Raft-replicated product service.

Retry strategy for write RPCs:
  During normal operation a non-leader replica returns UNAVAILABLE immediately.
  During Raft re-election (150-300 ms) ALL replicas are leaderless, so round-
  robining to a different replica does not help.  The stub therefore retries the
  SAME call up to MAX_ATTEMPTS times with BACKOFF_MS sleep between attempts
  before moving to the next replica.  This makes the re-election latency spike
  visible in the performance report (as required by the spec) rather than hiding
  it behind blind round-robin.

Failure modes handled:
  - grpc.StatusCode.UNAVAILABLE  — returned by product_server when pysyncobj
    callback fires with err != None (FAIL / not-leader / election in progress).
  - grpc.StatusCode.DEADLINE_EXCEEDED — network / timeout transient failure.
  - Any other RpcError — propagated immediately (not a transient cluster issue).
"""

import sys
import time
import logging
from pathlib import Path

import grpc

# Project root for db_layer/product/config.py imports.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
# db_layer/product/ so that `import product_pb2` resolves regardless of CWD.
sys.path.insert(0, str(Path(__file__).parent))

import product_pb2
import product_pb2_grpc

from db_layer.product.config import PRODUCT_GRPC_REPLICAS

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3        # retries on the same or next replica
BACKOFF_S    = 0.1      # 100 ms between attempts during re-election

_RETRY_CODES = {
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED,
}


class ResilientProductStub:
    """
    Round-robin stub over all 5 product gRPC replicas with backoff retry.

    On UNAVAILABLE or DEADLINE_EXCEEDED, retries up to MAX_ATTEMPTS times
    (with BACKOFF_S sleep between each) before rotating to the next replica.
    This ensures the re-election window is correctly reflected in latency
    rather than masked by immediate round-robin.
    """

    def __init__(self, replicas=None):
        self._replicas = replicas or PRODUCT_GRPC_REPLICAS
        self._idx = 0
        self._stubs = [
            product_pb2_grpc.ProductServiceStub(
                grpc.insecure_channel(f"{r['host']}:{r['port']}")
            )
            for r in self._replicas
        ]

    def _call(self, method_name: str, request):
        n = len(self._stubs)
        # Try each replica in turn; within each replica do MAX_ATTEMPTS retries.
        for replica_attempt in range(n):
            stub = self._stubs[self._idx]
            addr = f"{self._replicas[self._idx]['host']}:{self._replicas[self._idx]['port']}"

            for attempt in range(MAX_ATTEMPTS):
                try:
                    return getattr(stub, method_name)(request)
                except grpc.RpcError as exc:
                    if exc.code() in _RETRY_CODES:
                        logger.warning(
                            "Product replica %s returned %s (attempt %d/%d)",
                            addr, exc.code(), attempt + 1, MAX_ATTEMPTS,
                        )
                        if attempt < MAX_ATTEMPTS - 1:
                            time.sleep(BACKOFF_S)
                        # After exhausting attempts on this replica, break to next.
                    else:
                        raise

            # Move to next replica after exhausting retries on current one.
            self._idx = (self._idx + 1) % n
            logger.warning(
                "Rotating to product replica %d after %d failed attempts on %s",
                self._idx, MAX_ATTEMPTS, addr,
            )

        raise grpc.RpcError("All product replicas unavailable after retries")

    def __getattr__(self, name):
        return lambda req: self._call(name, req)


# Module-level singleton used by buyer/seller gRPC layers.
product_stub = ResilientProductStub()
