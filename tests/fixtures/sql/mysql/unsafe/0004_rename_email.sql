-- CHANGE renames and retypes at once: a broken deploy window and a table copy.
ALTER TABLE users CHANGE email primary_email varchar(255);
