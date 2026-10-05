-- -----------------------------------------------------------------------------
-- V004 — commerce.return_requests (T038)
--
-- Why this migration exists
-- -------------------------
-- US2's rule is that a *delivered* order belongs on the return path rather than the refund path.
-- This is where that decision lands. It mirrors V003 deliberately: the same two constraints make
-- "one logical request produces at most one live return" a property of the database rather than a
-- convention the service code is trusted to keep under concurrency.
--
--   1. `uq_return_requests_user_idempotency_key (user_id, idempotency_key)` — the retry guard, and
--      the key namespace belongs to the *user* for the same reason it does for refunds: a naive key
--      like "retry-1" is legitimate, a global unique key would let one user's request fail because
--      somebody else picked the same string, and that failure would itself reveal the collision.
--
--   2. `uq_return_requests_order_id_active` — the **partial** unique index behind "at most one live
--      return per order". Both constraints surface as SQLState 23505, so the constraint *name* is the
--      only thing that tells "the caller retried with the same key" apart from "somebody is trying to
--      open a second return for the same order". Tests assert the name literally for that reason.
--
--      The predicate is written as `status NOT IN (<terminal>)` rather than `status IN (<active>)` on
--      purpose: it fails closed. A status added later is treated as live until someone decides
--      otherwise, whereas an `IN` list would silently exempt every new status from the constraint.
--
--   3. `chk_return_requests_status` — the row can never represent an unknown status, whatever the
--      calling code does. The vocabulary mirrors the refund row's, so a return can be described with
--      the same lifecycle words; extending it later is a migration, not a code convention.
--
-- Why the id is a UUID string rather than an enumerable `return-001`
-- ---------------------------------------------------------------
-- Same reasoning as V003 (and T019 before it): concealment is a judgement about *guessability*.
-- `order-001` is enumerable and therefore needs 404-concealment; a random UUIDv4 confirms nothing, so
-- the read endpoints do not have to hide their existence either.
--
-- Deliberately NOT here: `version`. V1 returns are immutable after creation (status stays CREATED;
-- transitions arrive with the return-processing work), so a concurrency token nobody reads would be
-- dead schema. When transitions land, that change must add the token *and* keep `updated_at` fresh --
-- see the note on `updated_at` below.
-- -----------------------------------------------------------------------------

CREATE TABLE commerce.return_requests (
    id                     VARCHAR(64)    PRIMARY KEY,
    order_id               VARCHAR(64)    NOT NULL,
    user_id                VARCHAR(64)    NOT NULL,
    reason_code            VARCHAR(100)   NOT NULL,
    status                 VARCHAR(32)    NOT NULL,
    idempotency_key        VARCHAR(128)   NOT NULL,
    -- Provenance: which deterministic rule authorised this return. On the row rather than only in the
    -- audit log, so "why was this accepted?" stays answerable from the business record itself.
    eligibility_rule_code  VARCHAR(100)   NOT NULL,
    -- Always NULL in V1: no authoritative approval record exists yet (US4 / T049+). The column exists
    -- so that the future approval binding does not require rewriting history.
    approval_request_id    VARCHAR(64),
    -- Opaque Agent-run correlation id. Java records it for traceability and MUST NOT authorise on it:
    -- `agent.agent_runs` belongs to the Agent service (separate role, separate schema), so this
    -- service cannot verify it and never treats it as identity.
    run_id                 VARCHAR(64)    NOT NULL,
    created_at             TIMESTAMPTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Maintained by the database on INSERT only. V1 rows are immutable; a future status-transition
    -- migration must add the update path (trigger or @UpdateTimestamp) or this column silently stops
    -- being true.
    updated_at             TIMESTAMPTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_return_requests_order
        FOREIGN KEY (order_id) REFERENCES commerce.orders(id),
    CONSTRAINT fk_return_requests_user
        FOREIGN KEY (user_id) REFERENCES commerce.users(id),
    CONSTRAINT uq_return_requests_user_idempotency_key
        UNIQUE (user_id, idempotency_key),
    CONSTRAINT chk_return_requests_status
        CHECK (status IN ('CREATED', 'PROCESSING', 'COMPLETED', 'REJECTED', 'CANCELLED'))
);

-- "At most one live return per order", enforced by the database. A rejected or cancelled return must
-- not block a later, legitimate one -- which is what makes the index partial. Note that `orders.@Version`
-- cannot express this at all: two brand-new return rows share no version to compare (T009 recorded the
-- same lesson for `shipments`, and V003 for refunds).
CREATE UNIQUE INDEX uq_return_requests_order_id_active
    ON commerce.return_requests(order_id)
    WHERE status NOT IN ('REJECTED', 'CANCELLED');

CREATE INDEX idx_return_requests_order_id
    ON commerce.return_requests(order_id);

CREATE INDEX idx_return_requests_user_created
    ON commerce.return_requests(user_id, created_at DESC);
