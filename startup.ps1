# --- 5 buyer gRPC replicas (customer DB, atomic broadcast) ---
.\run_buyer_replica.ps1 0
.\run_buyer_replica.ps1 1
.\run_buyer_replica.ps1 2
.\run_buyer_replica.ps1 3
.\run_buyer_replica.ps1 4

# --- 5 seller gRPC replicas (customer DB, atomic broadcast) ---
.\run_seller_replica.ps1 0
.\run_seller_replica.ps1 1
.\run_seller_replica.ps1 2
.\run_seller_replica.ps1 3
.\run_seller_replica.ps1 4

# --- 5 product DB replicas (Raft) ---
.\run_product_replica.ps1 0
.\run_product_replica.ps1 1
.\run_product_replica.ps1 2
.\run_product_replica.ps1 3
.\run_product_replica.ps1 4

# --- financial SOAP service ---
python server\financial\financial_soap.py

# --- 4 seller REST replicas ---
.\run_seller_rest.ps1 0
.\run_seller_rest.ps1 1
.\run_seller_rest.ps1 2
.\run_seller_rest.ps1 3

# --- 4 buyer REST replicas ---
.\run_buyer_rest.ps1 0
.\run_buyer_rest.ps1 1
.\run_buyer_rest.ps1 2
.\run_buyer_rest.ps1 3

# --- clients ---
python client\seller\seller.py
python client\buyer\buyer.py
