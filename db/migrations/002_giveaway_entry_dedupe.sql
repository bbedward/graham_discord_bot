-- Applied automatically at bot startup by DBConfig.run_migrations(). Independent of 001.
--
-- One entry row per user per giveaway. The index will not build while duplicates exist - if
-- startup fails here, find them with the query below, collapse pending rows into the oldest row
-- for the pair (or delete them if the giveaway already ended), and restart. Rows already sent
-- (block_hash IS NOT NULL) cannot be merged.
--
--   SELECT giveaway_id, sending_user_id, count(*) AS rows,
--          sum(amount::numeric) AS total_raw, min(created_at), max(created_at)
--   FROM transactions
--   WHERE giveaway_id IS NOT NULL
--   GROUP BY giveaway_id, sending_user_id
--   HAVING count(*) > 1
--   ORDER BY rows DESC;

CREATE UNIQUE INDEX IF NOT EXISTS transactions_giveaway_sender_uniq
    ON transactions (giveaway_id, sending_user_id)
    WHERE giveaway_id IS NOT NULL;
