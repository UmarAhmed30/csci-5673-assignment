# Docker (PA3 stack)

**Command cheat sheet:** [docker/COMMANDS.md](COMMANDS.md) (copy-paste `docker compose` and script invocations). **GCP 3-VM example:** same file plus [docker/env.gcp.example](env.gcp.example).

The stack is split into **Compose fragments** under `docker/compose/` so you can run layers on different hosts. The root `docker-compose.yml` **includes** all fragments (Compose v2.20+) for a single-command local bring-up.

## What runs where

| Layer | Compose file | Contents |
|--------|----------------|----------|
| **DB** | `docker/compose/db.yml` | One **MySQL 8** container. After `db-init`, you have **10 databases**: `customer_db_0`–`customer_db_4` and `product_db_0`–`product_db_4` (not 10 separate `mysqld` processes—one server, ten schemas). |
| **gRPC** | `docker/compose/grpc.yml` | 5× product (Raft), 5× seller (broadcast), 5× buyer (broadcast). |
| **Financial** | `docker/compose/financial.yml` | SOAP card service. |
| **REST** | `docker/compose/rest.yml` | **5× seller-rest** and **5× buyer-rest** HTTP frontends. |

Other files: `docker/Dockerfile` (Python app image), `docker/Dockerfile.data-layer` (optional DB+app combo), `docker/mysql/init/` (creates `umar` on first MySQL start).

## One machine (full stack)

```bash
cd /path/to/csci-5673-assignment
cp docker/.env.example docker/.env
docker compose build
docker compose --env-file docker/.env up -d
```

Equivalent helper:

```bash
./scripts/run-all-local.sh up -d
```

### Published ports (defaults)

- **MySQL**: `localhost:${MYSQL_PORT:-3307}` → container `3306`
- **Seller REST**: `9020`–`9024` → internal `9002` (override with `SELLER_REST_HOST_PORT_0`, … `_4`)
- **Buyer REST**: `9120`–`9124` → internal `9001` (override with `BUYER_REST_HOST_PORT_0`, … `_4`)
- **Financial SOAP**: `${FINANCIAL_PORT:-8002}`
- **gRPC** (unchanged): seller `50061`–`50065`, buyer `50052`–`50056`, product `50070`–`50074`; Raft `7100`–`7104`; UDP seller `6200`–`6204`, buyer `6100`–`6104`

Inside the Compose network, services use DNS names: `mysql`, `financial`, `seller-grpc-0`, …

## Split across VMs

1. **DB VM**: run only the DB layer; open MySQL (`3306` or mapped port). Run `db-init` once (included in `db.yml` after MySQL is healthy).

2. **gRPC VM(s)**: from the repo (with the same image build):

   ```bash
   DB_HOST=<db-vm-ip> DB_PORT=3306 ./scripts/run-grpc.sh up -d
   ```

   If every peer is reachable by **IP:port** on one host, set the same IP for each `RAFT_NODE_*_HOST`, `SELLER_BC_*_HOST`, `BUYER_BC_*_HOST`, and `PRODUCT_GRPC_REPLICA_*_HOST` as needed (see `docker/compose/grpc.yml`).

3. **REST VM(s)**:

   ```bash
   DOCKER_SELLER_GRPC_REPLICA_0_HOST=<grpc-vm-ip> \
   DOCKER_BUYER_GRPC_REPLICA_0_HOST=<grpc-vm-ip> \
   DOCKER_FINANCIAL_SERVICE_HOST=<financial-vm-ip> \
   ./scripts/run-rest.sh up -d
   ```

   Use `DOCKER_*` names so a root `.env` meant for **host-run Python clients** (with `localhost` gRPC targets) does not override container wiring. Inside containers the app still sees `SELLER_GRPC_REPLICA_*_HOST`, etc.

4. **Financial**: run on any host; point REST at it with `DOCKER_FINANCIAL_SERVICE_HOST` / `DOCKER_FINANCIAL_SERVICE_PORT`.

### Layer-only scripts

| Script | Compose file |
|--------|----------------|
| `./scripts/run-db.sh` | `docker/compose/db.yml` |
| `./scripts/run-grpc.sh` | `docker/compose/grpc.yml` |
| `./scripts/run-financial.sh` | `docker/compose/financial.yml` |
| `./scripts/run-rest.sh` | `docker/compose/rest.yml` |

Pass through normal compose args, e.g. `./scripts/run-db.sh logs -f mysql`.

## Clients (host) and 5 REST replicas

Configure failover in root `.env` with `SELLER_REST_REPLICA_0_HOST` … `SELLER_REST_REPLICA_4_HOST` (and ports `9020`–`9024`), and the same pattern for buyer `9120`–`9124`. The Python clients round-robin across **five** REST replicas.

## `db-init`

Runs `db/setup_customer_replicas.py` and `db/setup_product_replicas.py` once MySQL is healthy. Passwords must match `docker/mysql/init` and `docker/.env`.

## Legacy single-file note

Older instructions referred to one seller REST and one buyer REST on `9001`/`9002`. The modular stack uses **five** of each by default; adjust `.env` / published ports if you need the old single-port layout for scripts.
