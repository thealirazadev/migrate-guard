-- MySQL 8.0 adds a column with a default instantly, with no rewrite.
ALTER TABLE users ADD COLUMN status varchar(20) NOT NULL DEFAULT 'active';
