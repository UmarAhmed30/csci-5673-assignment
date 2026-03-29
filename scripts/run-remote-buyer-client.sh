#!/usr/bin/env bash
# Buyer CLI → remote REST (5 replicas on ports 9120–9124). Run from repo root:
#   ./scripts/run-remote-buyer-client.sh
#   REST_HOST=34.63.168.86 ./scripts/run-remote-buyer-client.sh
#
# Default REST_HOST is rest-server external nic0 from docker/COMMANDS.md; override if you use the other NIC.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export REST_HOST="${REST_HOST:-34.9.1.238}"
export SESSION_TIMEOUT_SECS="${SESSION_TIMEOUT_SECS:-300}"

export BUYER_SERVER_HOST="$REST_HOST"
export BUYER_SERVER_PORT="${BUYER_SERVER_PORT:-9120}"

for i in 0 1 2 3 4; do
  export "BUYER_REST_REPLICA_${i}_HOST=$REST_HOST"
  export "BUYER_REST_REPLICA_${i}_PORT=$((9120 + i))"
done

exec python3 client/buyer/buyer.py "$@"
