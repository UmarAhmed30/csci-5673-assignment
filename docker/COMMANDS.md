# Commands to run PA3 Docker components

Run all commands from the **repository root** unless noted.

## One-time setup

```bash
cd /path/to/csci-5673-assignment
cp docker/.env.example docker/.env
# Edit docker/.env: MYSQL_ROOT_PASSWORD, DB_PASSWORD, MYSQL_PORT (optional)
docker compose build
```

---

## GCP three VMs (db-instance · grpc-layer · rest-server)

Use **internal IPs** on the same VPC for VM→VM traffic (lower latency, no extra egress). Example layout uses **nic0** (`10.128.0.x`); if you route over **nic1** (`10.0.0.x`), substitute those addresses consistently.

| VM | Role | Internal (nic0 / nic1) | External (nic0 / nic1) |
|----|------|-------------------------|-------------------------|
| **db-instance** | MySQL + `db-init` | 10.128.0.8 / 10.0.0.6 | 136.112.129.107 / 34.44.143.105 |
| **grpc-layer** | product / seller / buyer gRPC + **financial** (recommended) | 10.128.0.7 / 10.0.0.5 | 34.45.175.52 / 34.136.42.189 |
| **rest-server** | 5× seller REST + 5× buyer REST | 10.128.0.6 / 10.0.0.4 | 34.9.1.238 / 34.63.168.86 |

**Firewall / VPC:** allow **TCP 3306** from `grpc-layer` → `db-instance`. Allow **TCP** (gRPC + Raft + SOAP ports) and **UDP** (broadcast) from `rest-server` → `grpc-layer` as needed. See `## Default host ports` below.

**Order:** (1) **db-instance** → wait for `db-init` OK → (2) **grpc-layer** with `DB_HOST=10.128.0.8` → (3) **rest-server** with gRPC/financial pointing at `10.128.0.7`.

### 1) db-instance — database only

SSH to **db-instance**, clone repo, then:

```bash
cp docker/.env.example docker/.env
# Set MYSQL_ROOT_PASSWORD, DB_PASSWORD; set MYSQL_PORT=3306 if exposing MySQL to other VMs
docker compose -f docker/compose/db.yml --env-file docker/.env up -d
docker compose -f docker/compose/db.yml --env-file docker/.env logs -f db-init
```

Wait until `db-init` exits **0**.

### 2) grpc-layer — gRPC + financial (SOAP on same VM)

SSH to **grpc-layer**:

```bash
cp docker/.env.example docker/.env
# In docker/.env set:
#   DB_PASSWORD=<same as db-instance>
#   DB_HOST=10.128.0.8
#   DB_PORT=3306

export DB_HOST=10.128.0.8
export DB_PORT=3306
docker compose -f docker/compose/grpc.yml --env-file docker/.env up -d
docker compose -f docker/compose/financial.yml --env-file docker/.env up -d
```

Or use scripts (after exporting `DB_HOST` / `DB_PORT`):

```bash
export DB_HOST=10.128.0.8 DB_PORT=3306
./scripts/run-grpc.sh up -d
./scripts/run-financial.sh up -d
```

### 3) rest-server — HTTP REST only

SSH to **rest-server**. Point all replica hosts at **grpc-layer** internal IP `10.128.0.7` (same IP, different ports on that host). Point financial at the same VM if SOAP runs there:

```bash
cp docker/.env.example docker/.env
```

Append or merge from `docker/env.gcp.example`, then:

```bash
export DOCKER_SELLER_GRPC_REPLICA_0_HOST=10.128.0.7
export DOCKER_SELLER_GRPC_REPLICA_1_HOST=10.128.0.7
export DOCKER_SELLER_GRPC_REPLICA_2_HOST=10.128.0.7
export DOCKER_SELLER_GRPC_REPLICA_3_HOST=10.128.0.7
export DOCKER_SELLER_GRPC_REPLICA_4_HOST=10.128.0.7
export DOCKER_BUYER_GRPC_REPLICA_0_HOST=10.128.0.7
export DOCKER_BUYER_GRPC_REPLICA_1_HOST=10.128.0.7
export DOCKER_BUYER_GRPC_REPLICA_2_HOST=10.128.0.7
export DOCKER_BUYER_GRPC_REPLICA_3_HOST=10.128.0.7
export DOCKER_BUYER_GRPC_REPLICA_4_HOST=10.128.0.7
export DOCKER_FINANCIAL_SERVICE_HOST=10.128.0.7
export DOCKER_FINANCIAL_SERVICE_PORT=8002

./scripts/run-rest.sh up -d
```

**Clients / browsers** from the internet: use **rest-server** external IP (e.g. `34.9.1.238` or `34.63.168.86`) and mapped ports **9020–9024** (seller) / **9120–9124** (buyer). Open those in GCP firewall for your client source ranges.

**Reference copy-paste env:** see `docker/env.gcp.example`.

---

## Full stack (everything on one machine)

Uses root `docker-compose.yml` (includes `docker/compose/*.yml`).

```bash
docker compose --env-file docker/.env up -d
```

Helper (same thing):

```bash
./scripts/run-all-local.sh up -d
```

Check status:

```bash
docker compose ps
docker compose logs -f financial
```

Stop:

```bash
docker compose down
```

Stop and remove DB volume:

```bash
docker compose down -v
```

---

## Run layers separately (generic)

Use the same `docker/.env` for passwords/ports. Order for a **local** DB: **DB → gRPC → financial → REST** (or start DB + gRPC, then financial + REST).

### 1. Database (MySQL + `db-init`)

```bash
./scripts/run-db.sh up -d
```

Wait until `db-init` exits successfully:

```bash
docker compose -f docker/compose/db.yml --env-file docker/.env ps -a
docker compose -f docker/compose/db.yml --env-file docker/.env logs db-init
```

### 2. gRPC (product, seller, buyer replicas)

**Same machine as MySQL** (Compose service name `mysql`):

```bash
./scripts/run-grpc.sh up -d
```

**MySQL on another host** (set IP/port before `up`):

```bash
DB_HOST=203.0.113.10 DB_PORT=3306 ./scripts/run-grpc.sh up -d
```

### 3. Financial (SOAP)

```bash
./scripts/run-financial.sh up -d
```

### 4. REST (5× seller + 5× buyer HTTP)

**Same Docker network as gRPC + financial** (defaults):

```bash
./scripts/run-rest.sh up -d
```

**REST on another host** — point at gRPC and financial VMs (example):

```bash
export DOCKER_SELLER_GRPC_REPLICA_0_HOST=203.0.113.20
export DOCKER_BUYER_GRPC_REPLICA_0_HOST=203.0.113.20
export DOCKER_FINANCIAL_SERVICE_HOST=203.0.113.30
./scripts/run-rest.sh up -d
```

(Set `DOCKER_*_REPLICA_*` for each replica index 0–4 if hosts differ.)

---

## Raw `docker compose` (no scripts)

| Layer    | File |
|----------|------|
| DB       | `docker/compose/db.yml` |
| gRPC     | `docker/compose/grpc.yml` |
| Financial| `docker/compose/financial.yml` |
| REST     | `docker/compose/rest.yml` |

Example:

```bash
docker compose -f docker/compose/db.yml --env-file docker/.env up -d
docker compose -f docker/compose/grpc.yml --env-file docker/.env up -d
docker compose -f docker/compose/financial.yml --env-file docker/.env up -d
docker compose -f docker/compose/rest.yml --env-file docker/.env up -d
```

Merge DB + gRPC in one project (shared network):

```bash
docker compose -f docker/compose/db.yml -f docker/compose/grpc.yml --env-file docker/.env up -d
```

---

## Default host ports (after `up`)

| Component        | Host ports (defaults) |
|------------------|------------------------|
| MySQL            | `${MYSQL_PORT:-3307}` → 3306 |
| Seller REST      | 9020–9024 |
| Buyer REST       | 9120–9124 |
| Financial SOAP   | `${FINANCIAL_PORT:-8002}` |
| Seller gRPC TCP  | 50061–50065 |
| Buyer gRPC TCP   | 50052–50056 |
| Product gRPC TCP | 50070–50074 |
| Product Raft TCP | 7100–7104 |
| Seller UDP       | 6200–6204 |
| Buyer UDP        | 6100–6104 |

---

## Clients on the host

Point root `.env` at published REST ports (e.g. seller `9020`, buyer `9120`) and optional five replica entries — see `docker/README.md`.
