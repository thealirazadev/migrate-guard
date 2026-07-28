-- MG002 is a PostgreSQL rule: InnoDB builds this index online.
CREATE INDEX users_email_idx ON users (email);
