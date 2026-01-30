#!/bin/bash

mkdir distributed
cd distributed

apt-get update -y
apt-get install -y python3 python3-pip git


git clone https://github.com/UmarAhmed30/csci-5673-assignment.git .

python3 -m venv ./venv
source ./venv/bin/activate

pip3 install -r requirements.txt

cat <<EOF > .env
CUSTOMER_DB_HOST=136.115.191.148
CUSTOMER_DB_PORT=3306
CUSTOMER_DB_USER=root
CUSTOMER_DB_PASSWORD=Test@123
CUSTOMER_DB_NAME=customer_db

PRODUCT_DB_HOST=136.115.191.148
PRODUCT_DB_PORT=3306
PRODUCT_DB_USER=root
PRODUCT_DB_PASSWORD=Test@123
PRODUCT_DB_NAME=product_db

# Buyer Server Configuration
BUYER_SERVER_HOST=0.0.0.0
BUYER_SERVER_PORT=6000

# Seller Server Configuration
SELLER_SERVER_HOST=0.0.0.0
SELLER_SERVER_PORT=6001

# Session Configuration
SESSION_TIMEOUT_SECS=300
EOF

python3 server/seller/seller.py &
python3 server/buyer/buyer.py &

