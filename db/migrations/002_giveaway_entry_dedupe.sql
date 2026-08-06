-- Applied automatically at bot startup by DBConfig.run_migrations(). Independent of 001.
--
-- One PENDING entry row per user per giveaway. A duplicate pending row becomes a duplicate
-- on-chain send when the giveaway pays out. Scoped to block_hash IS NULL so historical rows
-- that were already sent (which legitimately include duplicates from before this fix) are
-- left alone and do not block the index build.
--
-- The index will not build while pending duplicates exist - if startup fails here, find them:
--
--   SELECT giveaway_id, sending_user_id, count(*)
--   FROM transactions
--   WHERE giveaway_id IS NOT NULL AND block_hash IS NULL
--   GROUP BY giveaway_id, sending_user_id
--   HAVING count(*) > 1;

CREATE UNIQUE INDEX IF NOT EXISTS transactions_giveaway_sender_pending_uniq
    ON transactions (giveaway_id, sending_user_id)
    WHERE giveaway_id IS NOT NULL AND block_hash IS NULL;
