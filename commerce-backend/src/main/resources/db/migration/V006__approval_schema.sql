-- -----------------------------------------------------------------------------
-- V006 — commerce.approval_requests (US4 / T051)
--
-- Why this migration exists
-- -------------------------
-- When a deterministic risk rule says `approvalRequired = true` (FR-009: the *rule* decides, never the
-- model and never retrieved text), the Agent must stop and wait instead of executing. This table is the
-- authoritative record of that pause: who asked, for what, and what a human decided.
--
-- **An approval is a binding, not a boolean.** Storing only "approved" is the accident this schema is
-- shaped to prevent: an approver who authorised order A for 199 must not thereby authorise order B, or
-- order A for 1999. So the four facts that define *what* was authorised -- run, order, action, amount --
-- are columns, and a decision is only usable for the exact tuple it was made against (T049's invariant,
-- re-checked on resume by T054 *after* re-reading this row, never from the Agent's memory).
--
-- Constraints, and why each is a database fact rather than a service convention
-- ---------------------------------------------------------------------------
--   1. `chk_approval_requests_status` — the row can never hold an unknown status. The vocabulary is the
--      one T049 tests: PENDING -> APPROVED | DENIED | EXPIRED, and terminal states are terminal.
--
--   2. `uq_approval_requests_intent_active` (partial) — "at most one *live* approval per intent". A
--      second request for the same (run, order, action) is a retry, not a second decision; two live
--      rows would let an approver approve one while the Agent read the other. The predicate is written
--      as `status NOT IN (<terminal>)` rather than `status = 'PENDING'` on purpose: it fails closed, so
--      a status added later is treated as live until someone decides otherwise (same reasoning as
--      V003/V004).
--
--   3. `chk_approval_requests_decided_has_time` — a terminal row without a decision timestamp is a lie,
--      and `decided_by` is what makes FR-026's "审批状态" auditable per run.
--
-- Why the id is a UUID string rather than an enumerable `approval-001`
-- ------------------------------------------------------------------
-- Same concealment reasoning as V003/V004: `order-001` is guessable and therefore needs 404-hiding; a
-- random UUIDv4 confirms nothing, so nothing has to be hidden. It is also the id the Agent is handed by
-- the *authority* (T053: the Agent must never mint an approval token or status itself).
--
-- Deliberately NOT here: the decision's free-text note (V1 keeps an auditable *fact* trail, and a
-- nullable comment field would invite the decision's reason to live in prose instead of `reason_code`),
-- and any column recording the *result* of the write that was authorised -- `return_requests.
-- approval_request_id` (V004) already carries that end of the link, and duplicating it here would give
-- the same fact two homes.
-- -----------------------------------------------------------------------------

CREATE TABLE commerce.approval_requests (
    id                     VARCHAR(64)    PRIMARY KEY,
    -- The Agent run that asked. Opaque correlation id, exactly as in V004: Java records it for
    -- traceability and MUST NOT authorise on it (that schema belongs to another service/role).
    run_id                 VARCHAR(64)    NOT NULL,
    order_id               VARCHAR(64)    NOT NULL,
    user_id                VARCHAR(64)    NOT NULL,
    -- What is being asked for, in the eligibility vocabulary (REFUND_ONLY / RETURN / RETURN_REFUND).
    action                 VARCHAR(32)    NOT NULL,
    -- The money half of the binding. NULL means "this action has no amount to authorise" (a pure
    -- return); the comparison on resume is on the value as decided, not on a re-derived one.
    amount                 NUMERIC(12, 2),
    status                 VARCHAR(32)    NOT NULL,
    -- Provenance: which deterministic rule demanded the approval. On the row, not only in the audit
    -- log, so "why did this need a human?" stays answerable from the business record itself (V004).
    eligibility_rule_code  VARCHAR(100)   NOT NULL,
    reason_code            VARCHAR(100)   NOT NULL,
    -- Set when a human decides; NULL while PENDING. The approver is a User with role APPROVER.
    decided_by             VARCHAR(64),
    decided_at             TIMESTAMPTZ,
    -- When the request stops being actionable. Expiry is a fact of the row, so EXPIRED is a status the
    -- database can explain rather than a state only a clock in application memory knows about.
    expires_at             TIMESTAMPTZ    NOT NULL,
    created_at             TIMESTAMPTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at             TIMESTAMPTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_approval_requests_order
        FOREIGN KEY (order_id) REFERENCES commerce.orders(id),
    CONSTRAINT fk_approval_requests_user
        FOREIGN KEY (user_id) REFERENCES commerce.users(id),
    CONSTRAINT fk_approval_requests_decided_by
        FOREIGN KEY (decided_by) REFERENCES commerce.users(id),
    CONSTRAINT chk_approval_requests_status
        CHECK (status IN ('PENDING', 'APPROVED', 'DENIED', 'EXPIRED')),
    CONSTRAINT chk_approval_requests_decided_has_time
        CHECK (status = 'PENDING' OR decided_at IS NOT NULL)
);

-- "At most one live approval per intent", enforced by the database. See note 2 in the header.
CREATE UNIQUE INDEX uq_approval_requests_intent_active
    ON commerce.approval_requests(run_id, order_id, action)
    WHERE status NOT IN ('APPROVED', 'DENIED', 'EXPIRED');

CREATE INDEX idx_approval_requests_order_id
    ON commerce.approval_requests(order_id);

-- The Approval Center's worklist: pending requests, newest first.
CREATE INDEX idx_approval_requests_status_created
    ON commerce.approval_requests(status, created_at DESC);
