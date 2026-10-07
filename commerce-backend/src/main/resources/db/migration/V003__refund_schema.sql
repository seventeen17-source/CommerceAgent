-- -----------------------------------------------------------------------------
-- V003 — commerce.refund_requests (T021 / T026)
--
-- Why this migration exists
-- -------------------------
-- This is the first table in the project that represents **money that has moved**. Its constraints,
-- not the service code, are what make "one logical request produces at most one logical refund"
-- true under concurrency:
--
--   1. `uq_refund_requests_user_idempotency_key (user_id, idempotency_key)` — the retry guard. The
--      key namespace belongs to the *user*, not to the whole table: a client may legitimately use a
--      naive key ("retry-1"), and a global unique key would make one user's request fail because
--      somebody else happened to pick the same string -- and the failure itself would reveal that
--      the key was already used elsewhere. Every lookup is owner-scoped too, so one user can never
--      read back another user's refund by presenting their key.
--
--   2. `uq_refund_requests_order_id_active` — the **partial** unique index that makes "at most one
--      live refund per order" a database fact rather than a service convention. It is partial on
--      purpose: a rejected or cancelled refund must not block a later, legitimate one. Note that
--      `orders.@Version` cannot express this at all -- two brand-new refund rows share no version to
--      compare (T009 recorded the same lesson for `shipments`).
--
--   3. `chk_refund_requests_amount` / `chk_refund_requests_status` — the row can never represent a
--      non-positive refund or an unknown status, whatever the calling code does.
--
-- Why the id is a UUID (varchar(64)) rather than an enumerable `refund-001`
-- ---------------------------------------------------------------
-- T019 established that concealment is a judgement about *guessability*: `order-001` is enumerable
-- and therefore needs 404-concealment, while a random UUIDv4 confirms nothing to an attacker. Refund
-- ids follow the same reasoning, so the read endpoints do not have to hide their existence.
--
-- Deliberately NOT here: `version`. data-model.md section 8 defines no optimistic-lock column for
-- this row, and in V1 a refund is immutable after creation (status stays CREATED; transitions arrive
-- with the settlement work). Adding a version column nobody reads would be dead schema. When status
-- transitions land, that change must add the concurrency token *and* keep `updated_at` fresh (see
-- the note on `updated_at` below).
-- -----------------------------------------------------------------------------

CREATE TABLE commerce.refund_requests (
    id                     VARCHAR(64)    PRIMARY KEY,
    order_id               VARCHAR(64)    NOT NULL,
    user_id                VARCHAR(64)    NOT NULL,
    reason_code            VARCHAR(100)   NOT NULL,
    amount                 NUMERIC(19, 2) NOT NULL,
    status                 VARCHAR(32)    NOT NULL,
    idempotency_key        VARCHAR(128)   NOT NULL,
    -- Provenance: which deterministic rule authorised this refund. Kept on the row (not only in the
    -- audit log) so "why was this paid?" is answerable from the business record itself.
    eligibility_rule_code  VARCHAR(100)   NOT NULL,
    -- Always NULL in V1: no authoritative approval record exists yet (US4 / T049+). The column
    -- exists so that the future approval binding does not require rewriting history.
    approval_request_id    VARCHAR(64),
    -- Opaque Agent-run correlation id. Java records it for traceability and MUST NOT authorise on
    -- it: `agent.agent_runs` is owned by the Agent service (separate DB role, separate schema), so
    -- this service cannot verify it and never treats it as identity.
    run_id                 VARCHAR(64)    NOT NULL,
    created_at             TIMESTAMPTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Maintained by the database on INSERT only. V1 rows are immutable; a future status-transition
    -- migration must add the update path (trigger or @UpdateTimestamp) or this column will silently
    -- stop being true.
    updated_at             TIMESTAMPTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_refund_requests_order
        FOREIGN KEY (order_id) REFERENCES commerce.orders(id),
    CONSTRAINT fk_refund_requests_user
        FOREIGN KEY (user_id) REFERENCES commerce.users(id),
    CONSTRAINT uq_refund_requests_user_idempotency_key
        UNIQUE (user_id, idempotency_key),
    CONSTRAINT chk_refund_requests_amount
        CHECK (amount > 0),
    CONSTRAINT chk_refund_requests_status
        CHECK (status IN ('CREATED', 'PROCESSING', 'COMPLETED', 'REJECTED', 'CANCELLED'))
);

-- "At most one live refund per order", enforced by the database. The constraint name is asserted
-- literally by RefundIntegrationTest: the two unique violations below both surface as SQLState
-- 23505, and only the constraint name tells "the caller retried with the same key" apart from
-- "somebody is trying to open a second refund for the same order".
CREATE UNIQUE INDEX uq_refund_requests_order_id_active
    ON commerce.refund_requests(order_id)
    WHERE status NOT IN ('REJECTED', 'CANCELLED');

CREATE INDEX idx_refund_requests_order_id
    ON commerce.refund_requests(order_id);

CREATE INDEX idx_refund_requests_user_created
    ON commerce.refund_requests(user_id, created_at DESC);
