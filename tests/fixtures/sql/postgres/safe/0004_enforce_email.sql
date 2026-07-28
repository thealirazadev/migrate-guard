-- PostgreSQL 12 and later skip the SET NOT NULL scan when a validated CHECK
-- already proves no NULL exists.
ALTER TABLE users ADD CONSTRAINT users_email_nn CHECK (email IS NOT NULL) NOT VALID;

ALTER TABLE users VALIDATE CONSTRAINT users_email_nn;

ALTER TABLE users ALTER COLUMN email SET NOT NULL;
