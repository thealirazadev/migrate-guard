-- A constant default is metadata-only from PostgreSQL 11, so there is no rewrite
-- and no failure on existing rows.
ALTER TABLE users ADD COLUMN status text NOT NULL DEFAULT 'active';
