-- Goes with the giveaway entry locking change. Independent of the duplicate-send fix in 001.
--
-- Nothing at the database level currently stops a user from holding more than one entry row against
-- the same giveaway, and every entry row becomes a real on-chain send to the winner when the
-- giveaway ends.

-- Find any existing duplicates first, the unique index will not build until they are resolved:
--
--   SELECT giveaway_id, sending_user_id, count(*) AS rows,
--          sum(amount::numeric) AS total_raw, min(created_at), max(created_at)
--   FROM transactions
--   WHERE giveaway_id IS NOT NULL
--   GROUP BY giveaway_id, sending_user_id
--   HAVING count(*) > 1
--   ORDER BY rows DESC;
--
-- Rows already sent (block_hash IS NOT NULL) cannot be merged, the money has moved. Rows still
-- pending should be collapsed into the oldest row for that pair, or deleted if the giveaway has
-- already ended.

-- One entry row per user per giveaway, enforced by the database rather than by an application level
-- read-then-write. Partial index, so ordinary tips and withdrawals (giveaway_id IS NULL) are
-- unaffected.
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS transactions_giveaway_sender_uniq
    ON transactions (giveaway_id, sending_user_id)
    WHERE giveaway_id IS NOT NULL;
