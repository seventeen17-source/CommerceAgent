-- -----------------------------------------------------------------------------
-- V007 — commerce.support_tickets (US5 / T059)
--
-- A SupportTicket is the durable handoff object for work automation cannot safely finish.
-- It is deliberately not an authorization object and not a transcript:
--
--   * user_id is the authenticated owner recorded by Java.
--   * order_id is optional because some failures happen before an order can be resolved.
--   * reason_code is machine-readable; evidence_summary is a bounded structured summary.
--     Hidden chain-of-thought, raw prompts, credentials, and arbitrary model prose do not belong here.
--   * run_id is provenance only. As with refunds/returns/approvals, Java records it but never treats
--     an Agent-owned run id as identity or authorization.
--
-- There is intentionally no idempotency key in T059. The current contract defines a create
-- operation, not "exactly one ticket per run/order", and inventing a uniqueness rule here would
-- silently turn a later legitimate re-escalation into a database conflict. If US5 later requires
-- idempotent ticket creation, that rule must be stated first and added by migration with tests.
-- -----------------------------------------------------------------------------

CREATE TABLE commerce.support_tickets (
    id                VARCHAR(64)   PRIMARY KEY,
    user_id           VARCHAR(64)   NOT NULL,
    order_id          VARCHAR(64),
    category          VARCHAR(64)   NOT NULL,
    reason_code       VARCHAR(100)  NOT NULL,
    evidence_summary  VARCHAR(2000) NOT NULL,
    status            VARCHAR(32)   NOT NULL,
    run_id            VARCHAR(64)   NOT NULL,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_support_tickets_user
        FOREIGN KEY (user_id) REFERENCES commerce.users(id),
    CONSTRAINT fk_support_tickets_order
        FOREIGN KEY (order_id) REFERENCES commerce.orders(id),
    CONSTRAINT chk_support_tickets_status
        CHECK (status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED'))
);

CREATE INDEX idx_support_tickets_user_created
    ON commerce.support_tickets(user_id, created_at DESC);

CREATE INDEX idx_support_tickets_order_id
    ON commerce.support_tickets(order_id)
    WHERE order_id IS NOT NULL;

CREATE INDEX idx_support_tickets_run_id
    ON commerce.support_tickets(run_id);
