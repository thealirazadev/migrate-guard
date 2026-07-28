-- NOT NULL with no default fails as soon as users holds a row.
ALTER TABLE users ADD COLUMN status varchar(20) NOT NULL;
