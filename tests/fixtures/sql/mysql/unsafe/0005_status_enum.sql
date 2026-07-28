-- Restating the member list can drop or reorder values invisibly.
ALTER TABLE orders MODIFY status ENUM('new', 'paid');
