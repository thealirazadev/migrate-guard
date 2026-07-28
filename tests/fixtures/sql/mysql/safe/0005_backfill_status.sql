-- Data only: no schema statement, so the file stays one transaction.
UPDATE users SET status = 'active' WHERE status IS NULL;

DELETE FROM users WHERE status = 'deleted';
