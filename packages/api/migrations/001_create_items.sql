CREATE TABLE IF NOT EXISTS items (
  id          SERIAL       PRIMARY KEY,
  name        VARCHAR(255) NOT NULL,
  description TEXT,
  view_count  INTEGER      NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
