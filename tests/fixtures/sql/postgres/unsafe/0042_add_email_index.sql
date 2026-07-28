-- Index build on a hot table with no CONCURRENTLY.
ALTER TABLE users ADD COLUMN email text;

CREATE INDEX users_email_idx ON users (email);
