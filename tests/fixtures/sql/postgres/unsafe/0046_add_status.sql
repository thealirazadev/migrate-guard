-- NOT NULL with no default fails the moment users holds a single row.
ALTER TABLE users ADD COLUMN status text NOT NULL;
