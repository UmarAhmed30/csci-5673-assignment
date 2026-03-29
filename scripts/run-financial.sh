#!/usr/bin/env bash
# Start SOAP financial service only.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec docker compose -f docker/compose/financial.yml --env-file docker/.env "$@"
