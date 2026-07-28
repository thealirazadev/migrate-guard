-- Immediate validation scans orders and locks both tables.
ALTER TABLE orders
    ADD CONSTRAINT orders_user_fk FOREIGN KEY (user_id) REFERENCES users (id);
