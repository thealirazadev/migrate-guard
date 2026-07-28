-- The index is built concurrently first, so attaching the constraint is instant.
CREATE UNIQUE INDEX CONCURRENTLY users_email_key ON users (email);

ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE USING INDEX users_email_key;
