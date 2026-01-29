# Marketplace - Distributed Systems - Programming Assignment 1

## System Design

This online marketplace consists of six distributed components communicating via TCP sockets: Client-Side Buyer Interface, Client-Side Seller Interface, Server-Side Buyer Interface, Server-Side Seller Interface, Customer Database and Product Database. All components run as separate processes and can be deployed on different machines. The frontend servers are stateless with all persistent state (sessions, carts, items) is stored in the backend MySQL databases. Sessions are identified by IDs and support automatic timeout after 5 minutes of inactivity. Communication uses raw TCP sockets with length-prefixed JSON messages.

## Assumptions

1. **Search Semantics**: Search uses exact keyword matching with OR logic (matches ANY provided keyword), case-sensitive, full-word only
2. **Session Management**: Sessions timeout after 5 minutes of inactivity. Clients must re-login after timeout
3. **Client Reconnection**: After login, if connection is lost with the server, clients automatically retry up to 3 times with 10-second delays between attempts
4. **Shopping Cart**: Unsaved cart items are deleted on logout. Only explicitly saved items persist across sessions
5. **Item ID**: Sequential auto-incrementing integer IDs assigned by the database for each new item
6. **Concurrent Access**: Multiple clients can connect simultaneously. Database handles concurrency through connection pooling
7. **Security**: Passwords stored in plaintext with basic authentication (to be enhanced in future assignments)
8. **Error Handling**: Invalid operations return descriptive error messages to clients

## Search Semantics

We adopted a simple **full word** search approach for the item search `SearchItemsForSale`. We created a table **item_keywords** with two fields, namely **item_id** and **keyword** to hold the keywords associated with an item. On the search operation, we **join** this table with the items table and filter the items based on the requested category, availability and the presence of matching keywords. If keywords are provided, only items whose keywords exactly match one or more of the search terms are returned. Otherwise, all the available items within the requested category are returned. This way the search logic is straightforward, efficient and easy to extend based on future needs.


## Current State

### What Works?
- All APIs implemented except `MakePurchase`
- Account creation and login for buyers and sellers
- Session management with 5-minute timeout
- Item registration and inventory management
- Keyword-based search with exact matching
- Shopping cart operations with save functionality
- Item and seller feedback/ratings
- CLI interfaces for both buyer and seller

### Known Limitations
- `MakePurchase` API not implemented (as per assignment requirements)
- Passwords stored in plaintext (security to be addressed in future assignment)

## Setup Instructions

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure .env variables. Please find a sample below:
```
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

BUYER_SERVER_HOST=<host>
BUYER_SERVER_PORT=<port>

SELLER_SERVER_HOST=<host>
SELLER_SERVER_PORT=<port>

SESSION_TIMEOUT_SECS=300
```

### 3. Initialize Databases
```bash
mysql -u root -p < db/schema.sql
```

### 4. Start Servers (in separate terminals)
```bash
python server/buyer/buyer.py
python server/seller/seller.py
```

### 5. Start Clients (in separate terminals)
```bash
python client/buyer/buyer.py
python client/seller/seller.py
```

## Performance Evaluation

Run simulations to measure average response time and throughput:
```bash
python experiment_setup/simulate_seller.py
python experiment_setup/simulate_buyer.py
```

## Authors
- Darshan Vijayaraghavan
- Umar Ahmed Thameem Ahmed

**Course**: CSCI 5673 - Distributed Systems (Spring 2026)
