-- MySQL commits implicitly around DDL, so this file is not one transaction.
ALTER TABLE users ADD COLUMN nickname varchar(40);

UPDATE users SET nickname = 'unset' WHERE nickname IS NULL;
