#!/bin/bash
set -e
service mariadb start
sleep 2
mysql -u root -e "DROP USER IF EXISTS 'umar'@'%'; CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED BY '${DATA_LAYER_DB_PASSWORD:-Test@123}'; GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION; FLUSH PRIVILEGES;"
exec "$@"
