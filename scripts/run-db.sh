#!/usr/bin/env bash
# Start MySQL + one-shot db-init (10 DBs: customer_db_0..4, product_db_0..4).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec docker compose -f docker/compose/db.yml --env-file docker/.env "$@"
