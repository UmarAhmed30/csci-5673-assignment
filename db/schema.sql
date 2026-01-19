CREATE DATABASE IF NOT EXISTS marketplace;
USE marketplace;

-- Table Creation Commands

CREATE TABLE buyers (
    buyer_id INT AUTO_INCREMENT PRIMARY KEY,
    buyer_name VARCHAR(32) NOT NULL,
    password VARCHAR(64) NOT NULL,
    items_purchased INT DEFAULT 0
);

CREATE TABLE sellers (
    seller_id INT AUTO_INCREMENT PRIMARY KEY,
    seller_name VARCHAR(32) NOT NULL,
    password VARCHAR(64) NOT NULL,
    thumbs_up INT DEFAULT 0,
    thumbs_down INT DEFAULT 0,
    items_sold INT DEFAULT 0
);

CREATE TABLE sessions (
    session_id CHAR(36) PRIMARY KEY,
    user_id INT NOT NULL,
    user_type ENUM('buyer', 'seller') NOT NULL,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE items (
    item_id INT AUTO_INCREMENT PRIMARY KEY,
    seller_id INT NOT NULL,
    item_name VARCHAR(32),
    category INT,
    condition_type ENUM('new', 'used'),
    price FLOAT,
    quantity INT,
    thumbs_up INT DEFAULT 0,
    thumbs_down INT DEFAULT 0,
    FOREIGN KEY (seller_id) REFERENCES sellers(seller_id)
);

CREATE TABLE item_keywords (
    item_id INT,
    keyword VARCHAR(8),
    FOREIGN KEY (item_id) REFERENCES items(item_id)
);

CREATE TABLE cart (
    buyer_id INT,
    item_id INT,
    quantity INT,
    PRIMARY KEY (buyer_id, item_id),
    FOREIGN KEY (buyer_id) REFERENCES buyers(buyer_id),
    FOREIGN KEY (item_id) REFERENCES items(item_id)
);

CREATE TABLE purchases (
    buyer_id INT,
    item_id INT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
