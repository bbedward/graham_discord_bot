-- REQUIRED before deploying the duplicate-send fix.
--
-- Tortoise is initialised with generate_schemas(safe=True), which creates missing tables but never
-- ALTERs existing ones, so this has to be applied by hand. Apply it BEFORE the code, otherwise
-- every query against `transactions` will reference columns that do not exist yet.

BEGIN;

-- `retries` was a bare Python class attribute on the Transaction model, so it was never persisted.
-- Every pass of the 10 minute re-queue built a fresh object with retries back at 0, which meant the
-- "give up after 20 attempts" cap never actually stopped anything.
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS retries INT NOT NULL DEFAULT 0;

-- Terminal state, so a transaction that cannot be completed stops being re-queued forever.
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS failed BOOLEAN NOT NULL DEFAULT FALSE;

COMMIT;

-- Optional but recommended: quarantine anything currently stuck in the loop before starting the bot
-- with the new code, so it gets reconciled deliberately rather than automatically re-sent.
--
--   SELECT count(*), min(created_at), max(created_at)
--   FROM transactions WHERE block_hash IS NULL AND destination IS NOT NULL;
--
--   UPDATE transactions SET failed = TRUE
--   WHERE block_hash IS NULL AND destination IS NOT NULL
--     AND created_at < now() - interval '1 hour';
