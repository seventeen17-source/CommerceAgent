-- -----------------------------------------------------------------------------
-- V007 — harden commerce.approval_requests after V006 was already applied.
--
-- V006 was validated against a real dev database before the entity/repository half of T051 landed,
-- so changing that migration now would create a Flyway checksum failure. This follow-up keeps
-- migration history append-only and fixes three integrity gaps discovered while wiring the domain
-- model:
--
-- 1. approval amount must be able to represent every amount the authoritative order/eligibility
--    model can represent (NUMERIC(19,2)); V006 accidentally narrowed it to NUMERIC(12,2).
-- 2. only actual executable after-sales actions may be approved.
-- 3. decision metadata must agree with status, not merely "terminal has a timestamp".
-- -----------------------------------------------------------------------------

ALTER TABLE commerce.approval_requests
    ALTER COLUMN amount TYPE NUMERIC(19, 2);

ALTER TABLE commerce.approval_requests
    ADD CONSTRAINT chk_approval_requests_action
        CHECK (action IN ('REFUND_ONLY', 'RETURN', 'RETURN_REFUND'));

ALTER TABLE commerce.approval_requests
    DROP CONSTRAINT chk_approval_requests_decided_has_time;

ALTER TABLE commerce.approval_requests
    ADD CONSTRAINT chk_approval_requests_decision_metadata
        CHECK (
            (status = 'PENDING' AND decided_at IS NULL AND decided_by IS NULL)
            OR
            (status = 'EXPIRED' AND decided_at IS NOT NULL AND decided_by IS NULL)
            OR
            (status IN ('APPROVED', 'DENIED') AND decided_at IS NOT NULL AND decided_by IS NOT NULL)
        );
