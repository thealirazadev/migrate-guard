-- Everything here touches a table created in this file: no rows, no traffic.
CREATE TABLE sessions (
    id bigint NOT NULL AUTO_INCREMENT PRIMARY KEY,
    token varchar(64) NOT NULL,
    scratch varchar(20)
);

ALTER TABLE sessions ADD UNIQUE KEY sessions_token_key (token);

ALTER TABLE sessions DROP COLUMN scratch;
