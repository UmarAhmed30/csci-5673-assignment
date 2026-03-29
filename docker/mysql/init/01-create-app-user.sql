-- gRPC/db-init use root + DB_PASSWORD from docker/.env (must match MYSQL_ROOT_PASSWORD).
-- Legacy `umar` user removed; remote connections use root@'%' with the same password.
DROP USER IF EXISTS 'umar'@'%';

CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED BY 'Test@123';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;
FLUSH PRIVILEGES;
