.\run_replica.ps1 0
.\run_replica.ps1 1
.\run_replica.ps1 2
.\run_replica.ps1 3
.\run_replica.ps1 4

.\run_seller_replica.ps1 0
.\run_seller_replica.ps1 1
.\run_seller_replica.ps1 2
.\run_seller_replica.ps1 3
.\run_seller_replica.ps1 4

python server\financial\financial_soap.py

python server\seller\seller_rest.py
python client\seller\seller.py

python server\buyer\buyer_rest.py
python client\buyer\buyer.py