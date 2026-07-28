-- MG006 and MG007 are PostgreSQL rules; MySQL has no NOT VALID form.
ALTER TABLE orders ADD CONSTRAINT orders_user_fk FOREIGN KEY (user_id) REFERENCES users (id);

ALTER TABLE users ADD UNIQUE KEY users_email_key (email);
