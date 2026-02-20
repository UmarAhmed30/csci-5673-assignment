# Marketplace - Distributed Systems - Programming Assignment 2

## System Design

This online marketplace is a distributed system with seven components communicating via different protocols. The frontend REST servers (Buyer and Seller) are stateless, delegating all state management to backend gRPC database services. Client applications interact with REST servers over HTTP, REST servers communicate with database layers via gRPC, and purchase transactions are validated through a SOAP-based financial service. All components run as independent processes and can be deployed across multiple machines. Session management uses token-based authentication with automatic 5-minute timeout for inactive sessions.

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
- **REST Servers ↔ Database Layer**: gRPC (Protocol Buffers)
- **Buyer Server ↔ Financial Service**: SOAP/WSDL

### Components
1. **Buyer Client** (`client/buyer/buyer.py`): CLI interface for buyers using REST APIs
2. **Seller Client** (`client/seller/seller.py`): CLI interface for sellers using REST APIs
3. **Buyer REST Server** (`server/buyer/buyer_rest.py`): Stateless FastAPI server on port 8000
4. **Seller REST Server** (`server/seller/seller_rest.py`): Stateless FastAPI server on port 8001
5. **Buyer gRPC Service** (`db_layer/buyer/buyer.py`): Database layer on port 50052
6. **Seller gRPC Service** (`db_layer/seller/seller.py`): Database layer on port 50051
7. **Financial SOAP Service** (`server/financial/financial_soap.py`): Payment processing on port 8002

## Search Semantics

We adopted a simple **full word** search approach for the item search `SearchItemsForSale`. We created a table **item_keywords** with two fields, namely **item_id** and **keyword** to hold the keywords associated with an item. On the search operation, we **join** this table with the items table and filter the items based on the requested category, availability and the presence of matching keywords. If keywords are provided, only items whose keywords exactly match one or more of the search terms are returned. Otherwise, all the available items within the requested category are returned. This way the search logic is straightforward, efficient and easy to extend based on future needs.


## Current State

### What Works?
- All APIs fully implemented including `MakePurchase`
- RESTful client-server communication using FastAPI
- gRPC communication between REST servers and databases
- SOAP-based financial transaction service
- Account creation and login for buyers and sellers with duplicate login prevention
- Session management with 5-minute timeout
- Item registration and inventory management
- Keyword-based search with exact matching
- Shopping cart operations with save functionality
- Purchase processing with credit card validation
- Item and seller feedback/ratings with quantity tracking in purchase history
- CLI interfaces for both buyer and seller

### Known Limitations
- Passwords stored in plaintext
- Financial service uses simulated validation (90% success rate)

## Setup Instructions

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure .env variables. Please find a sample below:
```
# MySQL Database Configuration
CUSTOMER_DB_HOST=<host>
CUSTOMER_DB_PORT=<port>
CUSTOMER_DB_USER=<username>
CUSTOMER_DB_PASSWORD=<password>
CUSTOMER_DB_NAME=customer_db

PRODUCT_DB_HOST=<host>
PRODUCT_DB_PORT=<port>
PRODUCT_DB_USER=<username>
PRODUCT_DB_PASSWORD=<password>
PRODUCT_DB_NAME=product_db

# REST Server Configuration
BUYER_SERVER_HOST=<host>
BUYER_SERVER_PORT=<port>

SELLER_SERVER_HOST=<host>
SELLER_SERVER_PORT=<port>

# gRPC Server Configuration
SELLER_GRPC_BIND_HOST=0.0.0.0
SELLER_GRPC_HOST=localhost
SELLER_GRPC_PORT=50051

BUYER_GRPC_BIND_HOST=0.0.0.0
BUYER_GRPC_HOST=localhost
BUYER_GRPC_PORT=50052

# SOAP Service Configuration
FINANCIAL_SERVICE_HOST=localhost
FINANCIAL_SERVICE_PORT=8002

# Session Configuration
SESSION_TIMEOUT_SECS=300
```

### 3. Initialize Databases
```bash
mysql -u root -p < db/schema.sql
```

### 4. Start All Services

Start services in the following order (each in a separate terminal):

#### Backend Services (gRPC)
```bash
# Start Seller gRPC Service (port 50051)
python db_layer/seller/seller.py

# Start Buyer gRPC Service (port 50052)
python db_layer/buyer/buyer.py
```

#### Frontend Services (REST and SOAP)
```bash
# Start Financial SOAP Service (port 8002)
python server/financial/financial_soap.py

# Start Buyer REST Server (port 8000)
python server/buyer/buyer_rest.py

# Start Seller REST Server (port 8001)
python server/seller/seller_rest.py
```

#### Client Applications
```bash
# Start Buyer Client
python client/buyer/buyer.py

# Start Seller Client
python client/seller/seller.py
```

### 5. API Documentation

Once servers are running, access interactive API documentation:
- Buyer Server: http://localhost:8000/docs
- Seller Server: http://localhost:8001/docs
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

# Copy to REST servers
copy db_layer/buyer/buyer_pb2.py server/buyer/
copy db_layer/buyer/buyer_pb2_grpc.py server/buyer/
copy db_layer/seller/seller_pb2.py server/seller/
copy db_layer/seller/seller_pb2_grpc.py server/seller/
```

## Authors
- Darshan Vijayaraghavan
- Umar Ahmed Thameem Ahmed

**Course**: CSCI 5673 - Distributed Systems (Spring 2026)
