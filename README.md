# Marketplace - Distributed Systems - Programming Assignment 3

## System Design

This online marketplace is a fault-tolerant distributed system. The PA3 stack runs **5 replicas** of every critical service. Buyer and seller gRPC database layers are replicated using **UDP atomic broadcast** (`broadcast/`). The product gRPC layer is replicated using **Raft consensus** (`pysyncobj`). Both the buyer and seller REST frontends run as 4 stateless replicas and clients round-robin across them. A SOAP-based financial service handles payment simulation. All components run as independent processes and can be deployed locally, via Docker, or across multiple VMs.

## Assumptions

1. **Search Semantics**: Search uses exact keyword matching with OR logic (matches ANY provided keyword), case-sensitive, full-word only
2. **Session Management**: Sessions timeout after 5 minutes of inactivity. Clients must re-login after timeout
3. **Shopping Cart**: Unsaved cart items are deleted on logout. Only explicitly saved items persist across sessions
4. **Item ID**: Sequential auto-incrementing integer IDs assigned by the database for each new item
5. **Concurrent Access**: Multiple clients can connect simultaneously. Database handles concurrency through connection pooling
6. **Security**: Passwords stored in plaintext with basic authentication
7. **Financial Transactions**: The SOAP-based financial service simulates payment processing with 90% success rate and 10% failure rate

## Architecture Overview

### Communication Protocols
- **Client ↔ REST Servers**: HTTP/REST APIs (FastAPI)
- **REST Servers ↔ Buyer/Seller gRPC**: gRPC (Protocol Buffers)
- **REST Servers ↔ Product gRPC**: gRPC (Protocol Buffers)
- **Buyer/Seller gRPC replicas**: UDP atomic broadcast (`broadcast/`)
- **Product gRPC replicas**: Raft consensus (pysyncobj) over TCP
- **Buyer Server ↔ Financial Service**: SOAP/WSDL

### Components

**Clients**
1. **Buyer Client** (`client/buyer/buyer.py`): CLI interface for buyers; round-robins across buyer REST replicas
2. **Seller Client** (`client/seller/seller.py`): CLI interface for sellers; round-robins across seller REST replicas

**REST Layer (5 replicas each)**

3. **Buyer REST Server** (`server/buyer/buyer_rest.py`): Stateless FastAPI servers on ports `9120–9124`
4. **Seller REST Server** (`server/seller/seller_rest.py`): Stateless FastAPI servers on ports `9020–9024`

**gRPC / Database Layer**

5. **Buyer gRPC Service** (`db_layer/buyer/buyer.py`): 5 replicas on ports `50052–50056`; replicated via UDP atomic broadcast on ports `6100–6104`
6. **Seller gRPC Service** (`db_layer/seller/seller.py`): 5 replicas on ports `50061–50065`; replicated via UDP atomic broadcast on ports `6200–6204`
7. **Product gRPC Service** (`db_layer/product/product_server.py`): 5 replicas on ports `50070–50074`; replicated via Raft on TCP ports `7100–7104`

**Other**

8. **Broadcast Module** (`broadcast/`): UDP sequencer-based atomic broadcast used by buyer and seller gRPC replicas
9. **Financial SOAP Service** (`server/financial/financial_soap.py`): Payment processing on port `8002`

## Replication & Fault Tolerance

### Buyer gRPC (atomic broadcast)
- 5 replicas, each backed by its own MySQL schema (`customer_db_0` … `customer_db_4`)
- Replicas coordinate writes using UDP atomic broadcast; all replicas apply operations in the same order
- gRPC ports: `50052–50056`
- Broadcast UDP ports: `6100–6104`

### Seller gRPC (atomic broadcast)
- 5 replicas, each backed by its own MySQL schema (`customer_db_0` … `customer_db_4`)
- Same broadcast mechanism as buyer
- gRPC ports: `50061–50065`
- Broadcast UDP ports: `6200–6204`

### Product gRPC (Raft)
- 5 replicas, each backed by its own MySQL schema (`product_db_0` … `product_db_4`)
- Uses `pysyncobj` for Raft-based leader election and log replication
- gRPC ports: `50070–50074`
- Raft TCP ports: `7100–7104`

### REST Layer
- 4 buyer REST replicas (ports `9120–9124`) and 4 seller REST replicas (ports `9020–9024`)
- Clients round-robin across all replicas for load distribution

## Search Semantics

We adopted a simple **full word** search approach for `SearchItemsForSale`. We created a table **item_keywords** with two fields, namely **item_id** and **keyword** to hold the keywords associated with an item. On the search operation, we **join** this table with the items table and filter the items based on the requested category, availability and the presence of matching keywords. If keywords are provided, only items whose keywords exactly match one or more of the search terms are returned. Otherwise, all the available items within the requested category are returned.

## Current State

### What Works?
- All APIs fully implemented including `MakePurchase`
- RESTful client-server communication using FastAPI
- gRPC communication between REST servers and database layers
- SOAP-based financial transaction service
- Account creation and login for buyers and sellers with duplicate login prevention
- Session management with 5-minute timeout
- Item registration and inventory management
- Keyword-based search with exact matching
- Shopping cart operations with save functionality
- Purchase processing with credit card validation
- Item and seller feedback/ratings with quantity tracking in purchase history
- CLI interfaces for both buyer and seller
- 5-replica atomic broadcast replication for buyer and seller gRPC layers
- 5-replica Raft replication for product gRPC layer
- 4-replica stateless REST frontends with client-side round-robin

### Known Limitations
- Passwords stored in plaintext
- Financial service uses simulated validation (90% success rate)

## Setup Instructions

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Each service reads from environment variables. For **local development** copy the sample below into a `.env` file (or use the per-process `env.*` files alongside the PowerShell scripts):

```
# MySQL Database Configuration
CUSTOMER_DB_HOST=localhost
CUSTOMER_DB_PORT=3306
CUSTOMER_DB_USER=<username>
CUSTOMER_DB_PASSWORD=<password>
CUSTOMER_DB_NAME=customer_db_0

PRODUCT_DB_HOST=localhost
PRODUCT_DB_PORT=3306
PRODUCT_DB_USER=<username>
PRODUCT_DB_PASSWORD=<password>
PRODUCT_DB_NAME=product_db_0

# Buyer gRPC replicas (used by buyer REST servers)
BUYER_GRPC_REPLICA_0_HOST=localhost
BUYER_GRPC_REPLICA_0_PORT=50052
BUYER_GRPC_REPLICA_1_HOST=localhost
BUYER_GRPC_REPLICA_1_PORT=50053
BUYER_GRPC_REPLICA_2_HOST=localhost
BUYER_GRPC_REPLICA_2_PORT=50054
BUYER_GRPC_REPLICA_3_HOST=localhost
BUYER_GRPC_REPLICA_3_PORT=50055
BUYER_GRPC_REPLICA_4_HOST=localhost
BUYER_GRPC_REPLICA_4_PORT=50056

# Seller gRPC replicas (used by seller REST servers)
SELLER_GRPC_REPLICA_0_HOST=localhost
SELLER_GRPC_REPLICA_0_PORT=50061
SELLER_GRPC_REPLICA_1_HOST=localhost
SELLER_GRPC_REPLICA_1_PORT=50062
SELLER_GRPC_REPLICA_2_HOST=localhost
SELLER_GRPC_REPLICA_2_PORT=50063
SELLER_GRPC_REPLICA_3_HOST=localhost
SELLER_GRPC_REPLICA_3_PORT=50064
SELLER_GRPC_REPLICA_4_HOST=localhost
SELLER_GRPC_REPLICA_4_PORT=50065

# Product gRPC replicas (Raft-replicated; used by both REST servers)
PRODUCT_GRPC_REPLICA_0_HOST=localhost
PRODUCT_GRPC_REPLICA_0_PORT=50070
PRODUCT_GRPC_REPLICA_1_HOST=localhost
PRODUCT_GRPC_REPLICA_1_PORT=50071
PRODUCT_GRPC_REPLICA_2_HOST=localhost
PRODUCT_GRPC_REPLICA_2_PORT=50072
PRODUCT_GRPC_REPLICA_3_HOST=localhost
PRODUCT_GRPC_REPLICA_3_PORT=50073
PRODUCT_GRPC_REPLICA_4_HOST=localhost
PRODUCT_GRPC_REPLICA_4_PORT=50074

# REST Server replicas (used by clients)
BUYER_REST_REPLICA_0_HOST=localhost
BUYER_REST_REPLICA_0_PORT=9120
BUYER_REST_REPLICA_1_HOST=localhost
BUYER_REST_REPLICA_1_PORT=9121
BUYER_REST_REPLICA_2_HOST=localhost
BUYER_REST_REPLICA_2_PORT=9122
BUYER_REST_REPLICA_3_HOST=localhost
BUYER_REST_REPLICA_3_PORT=9123
BUYER_REST_REPLICA_4_HOST=localhost
BUYER_REST_REPLICA_4_PORT=9124

SELLER_REST_REPLICA_0_HOST=localhost
SELLER_REST_REPLICA_0_PORT=9020
SELLER_REST_REPLICA_1_HOST=localhost
SELLER_REST_REPLICA_1_PORT=9021
SELLER_REST_REPLICA_2_HOST=localhost
SELLER_REST_REPLICA_2_PORT=9022
SELLER_REST_REPLICA_3_HOST=localhost
SELLER_REST_REPLICA_3_PORT=9023
SELLER_REST_REPLICA_4_HOST=localhost
SELLER_REST_REPLICA_4_PORT=9024

# SOAP Service Configuration
FINANCIAL_SERVICE_HOST=localhost
FINANCIAL_SERVICE_PORT=8002

# Session Configuration
SESSION_TIMEOUT_SECS=300
```

### 3. Initialize Databases

PA3 uses 10 databases (5 customer, 5 product). Run the setup scripts once against a running MySQL instance:

```bash
python db/setup_customer_replicas.py   # creates customer_db_0 … customer_db_4
python db/setup_product_replicas.py    # creates product_db_0 … product_db_4
```

Both scripts accept `--drop` (drop and recreate) and `--no-seed` (skip seed data) flags.

---

## Option A: Docker (Recommended)

Docker Compose orchestrates the full stack. All configuration lives in `docker/.env`.

### One machine - full stack

```bash
cd /path/to/csci-5673-assignment
cp docker/.env.example docker/.env
# Edit docker/.env: set MYSQL_ROOT_PASSWORD and DB_PASSWORD at minimum
docker compose build
docker compose --env-file docker/.env up -d
```

Helper script (does the same thing):

```bash
./scripts/run-all-local.sh up -d
```

Check status and stop:

```bash
docker compose ps
docker compose logs -f
docker compose down          # stop
docker compose down -v       # stop and remove DB volume
```

### Layer-by-layer (start in order)

```bash
./scripts/run-db.sh up -d           # MySQL + db-init (wait for db-init exit 0)
./scripts/run-grpc.sh up -d         # 5× product (Raft) + 5× seller + 5× buyer gRPC
./scripts/run-financial.sh up -d    # Financial SOAP
./scripts/run-rest.sh up -d         # 5× seller REST + 5× buyer REST
```

Wait for `db-init` to finish before starting gRPC:

```bash
docker compose -f docker/compose/db.yml --env-file docker/.env logs -f db-init
```

### Default published ports after `up`

| Component | Host ports |
|-----------|-----------|
| MySQL | `${MYSQL_PORT:-3307}` |
| Seller REST | `9020–9024` |
| Buyer REST | `9120–9124` |
| Financial SOAP | `${FINANCIAL_PORT:-8002}` |
| Seller gRPC (TCP) | `50061–50065` |
| Buyer gRPC (TCP) | `50052–50056` |
| Product gRPC (TCP) | `50070–50074` |
| Product Raft (TCP) | `7100–7104` |
| Seller broadcast (UDP) | `6200–6204` |
| Buyer broadcast (UDP) | `6100–6104` |

### Split across multiple VMs (GCP / cloud)

For a 3-VM deployment (db-instance → grpc-layer → rest-server), see the full step-by-step instructions in [`docker/COMMANDS.md`](docker/COMMANDS.md). The `docker/gcp-vars.template` file contains ready-to-paste env blocks for each VM role.

---

## Option B: Windows — PowerShell (no Docker)

Each replica reads from a pre-configured `env.*` file. Run each command in a **separate terminal window** in the order shown below.

### 1. Initialize databases

```powershell
python db\setup_customer_replicas.py
python db\setup_product_replicas.py
```

### 2. Start buyer gRPC replicas (atomic broadcast, 5 nodes)

```powershell
.\run_buyer_replica.ps1 0
.\run_buyer_replica.ps1 1
.\run_buyer_replica.ps1 2
.\run_buyer_replica.ps1 3
.\run_buyer_replica.ps1 4
```

### 3. Start seller gRPC replicas (atomic broadcast, 5 nodes)

```powershell
.\run_seller_replica.ps1 0
.\run_seller_replica.ps1 1
.\run_seller_replica.ps1 2
.\run_seller_replica.ps1 3
.\run_seller_replica.ps1 4
```

### 4. Start product gRPC replicas (Raft, 5 nodes)

```powershell
.\run_product_replica.ps1 0
.\run_product_replica.ps1 1
.\run_product_replica.ps1 2
.\run_product_replica.ps1 3
.\run_product_replica.ps1 4
```

### 5. Start financial SOAP service

```powershell
python server\financial\financial_soap.py
```

### 6. Start seller REST replicas

```powershell
.\run_seller_rest.ps1 0
.\run_seller_rest.ps1 1
.\run_seller_rest.ps1 2
.\run_seller_rest.ps1 3
```

### 7. Start buyer REST replicas

```powershell
.\run_buyer_rest.ps1 0
.\run_buyer_rest.ps1 1
.\run_buyer_rest.ps1 2
.\run_buyer_rest.ps1 3
```

### 8. Run clients

```powershell
python client\seller\seller.py
python client\buyer\buyer.py
```

---

## API Documentation

Once REST servers are running, access interactive API documentation:
- Buyer REST (replica 0): http://localhost:9120/docs
- Seller REST (replica 0): http://localhost:9020/docs
- Financial Service WSDL: http://localhost:8002/?wsdl

## Performance Evaluation

Run simulations to measure average response time and throughput:

```bash
python experiment_setup/simulate_seller.py
python experiment_setup/simulate_buyer.py
```

## Protocol Buffer Compilation

If you modify `.proto` files, regenerate Python code:

```bash
# Buyer service
cd db_layer/buyer
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. buyer.proto
cd ../..

# Seller service
cd db_layer/seller
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. seller.proto
cd ../..

# Product service
cd db_layer/product
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. product.proto
cd ../..

# Copy generated files to REST servers
copy db_layer/buyer/buyer_pb2.py server/buyer/
copy db_layer/buyer/buyer_pb2_grpc.py server/buyer/
copy db_layer/seller/seller_pb2.py server/seller/
copy db_layer/seller/seller_pb2_grpc.py server/seller/
```

## Authors
- Darshan Vijayaraghavan
- Umar Ahmed Thameem Ahmed

**Course**: CSCI 5673 - Distributed Systems (Spring 2026)
