-- The constraint builds its backing index under ACCESS EXCLUSIVE.
ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE (email);
