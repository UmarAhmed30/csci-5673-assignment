#!/usr/bin/env bash
# Start 5× seller-rest + 5× buyer-rest.
# Point at gRPC + financial VMs (defaults work when merged with full stack on one machine).
# Examples:
#   ./scripts/run-rest.sh up -d
#   DOCKER_SELLER_GRPC_REPLICA_0_HOST=203.0.113.50 DOCKER_BUYER_GRPC_REPLICA_0_HOST=203.0.113.51 \
#     DOCKER_FINANCIAL_SERVICE_HOST=203.0.113.52 ./scripts/run-rest.sh up -d
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec docker compose -f docker/compose/rest.yml --env-file docker/.env "$@"
