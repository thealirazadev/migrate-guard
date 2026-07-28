-- Everything here touches a table created in this file: no rows, no traffic.
CREATE TABLE sessions (
    id bigserial PRIMARY KEY,
    token text NOT NULL,
    scratch text
);

CREATE INDEX sessions_token_idx ON sessions (token);

ALTER TABLE sessions DROP COLUMN scratch;
