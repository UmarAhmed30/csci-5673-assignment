-- Password must match DB_PASSWORD in docker/.env (default: dockerdb)
CREATE USER IF NOT EXISTS 'umar'@'%' IDENTIFIED BY 'dockerdb';
GRANT ALL PRIVILEGES ON *.* TO 'umar'@'%' WITH GRANT OPTION;
FLUSH PRIVILEGES;
