-- ============================================
-- Customer DB
-- ============================================
CREATE DATABASE IF NOT EXISTS customer_db;
USE customer_db;

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

-- Stub Commands for Customer DB

INSERT INTO buyers (buyer_name, password)
VALUES ("Umar", "umar");

INSERT INTO sellers (seller_name, password, thumbs_up, thumbs_down, items_sold)
VALUES
('Seller1', 'seller1', 10, 1, 5),
('Seller2', 'seller2', 3, 0, 2),
('Seller3', 'seller3', 0, 0, 0);

-- ============================================
-- Product DB
-- ============================================
CREATE DATABASE IF NOT EXISTS product_db;
USE product_db;

CREATE TABLE items (
    item_id INT AUTO_INCREMENT PRIMARY KEY,
    seller_id INT NOT NULL,
    item_name VARCHAR(32),
    category INT,
    condition_type ENUM('new', 'used'),
    price FLOAT,
    quantity INT,
    thumbs_up INT DEFAULT 0,
    thumbs_down INT DEFAULT 0
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
    saved BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (buyer_id, item_id),
    FOREIGN KEY (item_id) REFERENCES items(item_id)
);

CREATE TABLE purchases (
    buyer_id INT,
    item_id INT,
    quantity INT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE categories (
    category_id INT PRIMARY KEY,
    category_name VARCHAR(32) NOT NULL
);

-- Stub Commands for Product DB

INSERT INTO items (
    seller_id,
    item_name,
    category,
    condition_type,
    price,
    quantity,
    thumbs_up,
    thumbs_down
)
VALUES
(1, 'iPhone 12', 1, 'used', 599.99, 3, 5, 1),
(1, 'MacBook Air', 1, 'used', 899.50, 2, 8, 0),
(2, 'Office Chair', 2, 'new', 129.99, 10, 2, 0),
(2, 'Study Table', 2, 'used', 89.99, 5, 1, 1),
(3, 'Wireless Mouse', 3, 'new', 19.99, 25, 0, 0);

INSERT INTO item_keywords (item_id, keyword)
VALUES
(1, 'phone'),
(1, 'apple'),
(1, 'ios'),
(2, 'laptop'),
(2, 'apple'),
(2, 'mac'),
(3, 'chair'),
(3, 'office'),
(3, 'seat'),
(4, 'table'),
(4, 'desk'),
(4, 'study'),
(5, 'mouse'),
(5, 'wireless'),
(5, 'usb');

INSERT INTO categories (category_id, category_name)
VALUES
(1, 'Electronics'),
(2, 'Furniture'),
(3, 'Accessories'),
(4, 'Books'),
(5, 'Clothing');
