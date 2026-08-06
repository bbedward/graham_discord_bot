-- Applied automatically at bot startup by DBConfig.run_migrations().
-- generate_schemas(safe=True) never ALTERs existing tables, which is why these columns
-- ship as a migration.

BEGIN;

ALTER TABLE transactions ADD COLUMN IF NOT EXISTS retries INT NOT NULL DEFAULT 0;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS failed BOOLEAN NOT NULL DEFAULT FALSE;

-- Quarantine anything already stuck so it is reconciled deliberately by an admin instead of
-- re-sent on startup. Review with:
--   SELECT count(*), min(created_at), max(created_at)
--   FROM transactions WHERE failed = TRUE;
-- To release a row after review: UPDATE transactions SET failed = FALSE, retries = 0 WHERE id = ...;
-- the send path reconciles against the chain and adopts an existing block before publishing anything.
UPDATE transactions SET failed = TRUE
WHERE block_hash IS NULL AND destination IS NOT NULL
  AND created_at < now() - interval '1 hour';

COMMIT;
