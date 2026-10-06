-- -----------------------------------------------------------------------------
-- V005 — commerce.return_requests.return_deadline (T040)
--
-- Why this column exists
-- ----------------------
-- `POST /returns` promises the caller a `returnDeadline`, and that promise is a fact about *the day the
-- return was accepted*: the rule's return window measured from the carrier's signed-at timestamp. Recomputing
-- it on every read would let a later rule revision (or a re-seeded shipment) silently rewrite a deadline the
-- customer was already told. So it is frozen at creation — the same reasoning that keeps the refund row's
-- accepted amount on the refund row instead of deriving it again later.
--
-- Why it is nullable even though V1 always computes one
-- ----------------------------------------------------
-- The contract marks `returnDeadline` nullable, and the schema should not be stricter than a fact the API may
-- legitimately be unable to state. T039's decision only authorises a return when the window is computable (a
-- rule that declares no window, or a shipment with no signed-at fact, is refused *before* any write happens),
-- so every row V1 creates carries a value. A future rule that authorises a return without a window would
-- legally produce NULL, and that must not require rewriting this column.
--
-- Note the deadline is NOT a second source of truth for the window check: the decision (T039) compares
-- `now` against `returnDeadline`, and this column stores the value the write path froze at acceptance.
-- Both use the single `EligibilityService.returnDeadline` function.
--
-- Existing rows: none. V004 shipped inside the same US2 work and the write path that creates rows arrives
-- with this migration, so there is nothing to backfill and no invented value.
-- -----------------------------------------------------------------------------

ALTER TABLE commerce.return_requests
    ADD COLUMN return_deadline TIMESTAMPTZ;

-- -----------------------------------------------------------------------------
-- Also in V005 — `return_method` (T040)
--
-- The contract's `CreateReturnRequest` publishes `returnMethod`, so the endpoint must accept it. It is
-- stored rather than ignored for one concrete reason: it participates in the idempotency fingerprint,
-- and a field that decides "is this the same logical request?" has to be comparable against what the
-- first attempt stored. `reason_code` is stored for exactly the same reason.
--
-- Nullable because the contract marks it nullable, and V1 attaches no behaviour to it: no branch reads
-- it, no state depends on it. When the return-processing work gives it meaning, that migration must say
-- what the values are — this one deliberately does not invent a vocabulary.
-- -----------------------------------------------------------------------------

ALTER TABLE commerce.return_requests
    ADD COLUMN return_method VARCHAR(32);
