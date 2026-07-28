-- Concurrent build: writes to users keep flowing while the index is created.
CREATE INDEX CONCURRENTLY users_last_seen_idx ON users (last_seen_at);

CREATE UNIQUE INDEX CONCURRENTLY users_email_key ON users (email);
