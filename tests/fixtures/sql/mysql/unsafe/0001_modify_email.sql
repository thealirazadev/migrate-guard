-- MODIFY copies the whole table while holding a metadata lock.
ALTER TABLE users MODIFY email varchar(255) NOT NULL;
