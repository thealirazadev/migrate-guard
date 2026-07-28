-- Both old names disappear while the previous release still queries them.
ALTER TABLE users RENAME COLUMN email TO primary_email;

ALTER TABLE orders RENAME TO purchases;
