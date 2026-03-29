#!/bin/bash
set -e
service mariadb start
sleep 2
mysql -u root -e "CREATE USER IF NOT EXISTS 'umar'@'%' IDENTIFIED BY '${DATA_LAYER_DB_PASSWORD:-dockerdb}'; GRANT ALL PRIVILEGES ON *.* TO 'umar'@'%' WITH GRANT OPTION; FLUSH PRIVILEGES;"
exec "$@"
