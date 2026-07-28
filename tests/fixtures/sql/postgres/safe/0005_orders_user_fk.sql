-- NOT VALID skips the scan; the validation runs under SHARE UPDATE EXCLUSIVE.
ALTER TABLE orders
    ADD CONSTRAINT orders_user_fk FOREIGN KEY (user_id) REFERENCES users (id) NOT VALID;

ALTER TABLE orders VALIDATE CONSTRAINT orders_user_fk;
