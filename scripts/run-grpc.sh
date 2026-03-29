#!/usr/bin/env bash
# Start product + seller + buyer gRPC replicas.
# Usage:
#   ./scripts/run-grpc.sh up -d
# Remote MySQL VM:
#   DB_HOST=203.0.113.10 DB_PORT=3306 ./scripts/run-grpc.sh up -d
# Same VM, all peers by IP:
#   export RAFT_NODE_0_HOST=203.0.113.20  # ... or use defaults on single Docker network
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec docker compose -f docker/compose/grpc.yml --env-file docker/.env "$@"
