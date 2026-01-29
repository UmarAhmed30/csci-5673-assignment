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
    category_id INT NOT NULL,
    item_number INT NOT NULL,
    seller_id INT NOT NULL,
    item_name VARCHAR(32),
    condition_type ENUM('new', 'used'),
    price FLOAT,
    quantity INT,
    thumbs_up INT DEFAULT 0,
    thumbs_down INT DEFAULT 0,
    PRIMARY KEY (category_id, item_number)
);

CREATE TABLE item_keywords (
    category_id INT,
    item_number INT,
    keyword VARCHAR(8),
    FOREIGN KEY (category_id, item_number) REFERENCES items(category_id, item_number)
);

CREATE TABLE cart (
    buyer_id INT,
    category_id INT,
    item_number INT,
    quantity INT,
    saved BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (buyer_id, category_id, item_number),
    FOREIGN KEY (category_id, item_number) REFERENCES items(category_id, item_number)
);

CREATE TABLE purchases (
    buyer_id INT,
    category_id INT,
    item_number INT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE categories (
    category_id INT PRIMARY KEY,
    category_name VARCHAR(32) NOT NULL
);

-- Stub Commands for Product DB

INSERT INTO items (
    category_id,
    item_number,
    seller_id,
    item_name,
    condition_type,
    price,
    quantity,
    thumbs_up,
    thumbs_down
)
VALUES
(1, 1, 1, 'iPhone 12', 'used', 599.99, 3, 5, 1),
(1, 2, 1, 'MacBook Air', 'used', 899.50, 2, 8, 0),
(2, 1, 2, 'Office Chair', 'new', 129.99, 10, 2, 0),
(2, 2, 2, 'Study Table', 'used', 89.99, 5, 1, 1),
(3, 1, 3, 'Wireless Mouse', 'new', 19.99, 25, 0, 0);

INSERT INTO item_keywords (category_id, item_number, keyword)
VALUES
(1, 1, 'phone'),
(1, 1, 'apple'),
(1, 1, 'ios'),
(1, 2, 'laptop'),
(1, 2, 'apple'),
(1, 2, 'mac'),
(2, 1, 'chair'),
(2, 1, 'office'),
(2, 1, 'seat'),
(2, 2, 'table'),
(2, 2, 'desk'),
(2, 2, 'study'),
(3, 1, 'mouse'),
(3, 1, 'wireless'),
(3, 1, 'usb');

INSERT INTO categories (category_id, category_name)
VALUES
(1, 'Electronics'),
(2, 'Furniture'),
(3, 'Accessories'),
(4, 'Books'),
(5, 'Clothing');
