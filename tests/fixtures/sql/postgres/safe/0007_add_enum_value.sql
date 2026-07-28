-- Appending an enum member needs no drop and recreate.
ALTER TYPE order_status ADD VALUE 'refunded';
