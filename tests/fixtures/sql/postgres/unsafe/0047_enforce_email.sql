-- A bare SET NOT NULL scans the whole table under ACCESS EXCLUSIVE.
ALTER TABLE users ALTER COLUMN email SET NOT NULL;
