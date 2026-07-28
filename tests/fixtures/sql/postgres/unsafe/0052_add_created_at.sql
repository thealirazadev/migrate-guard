-- A volatile default is evaluated per row, so it rewrites on every version.
ALTER TABLE users ADD COLUMN created_at timestamptz NOT NULL DEFAULT now();
