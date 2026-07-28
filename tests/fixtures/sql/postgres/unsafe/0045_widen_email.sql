-- Retyping a live column rewrites every row under ACCESS EXCLUSIVE.
ALTER TABLE users ALTER COLUMN email TYPE varchar(255);
