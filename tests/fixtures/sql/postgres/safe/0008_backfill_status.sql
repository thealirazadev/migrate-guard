-- PostgreSQL DDL is transactional, so a mixed migration rolls back cleanly.
-- MG009 is a MySQL rule and stays quiet here.
ALTER TABLE users ADD COLUMN nickname text;

UPDATE users SET nickname = 'unset' WHERE nickname IS NULL;
