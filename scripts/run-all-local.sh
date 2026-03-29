#!/usr/bin/env bash
# Full stack on one machine (same as: docker compose up -d from repo root).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec docker compose --env-file docker/.env "$@"
