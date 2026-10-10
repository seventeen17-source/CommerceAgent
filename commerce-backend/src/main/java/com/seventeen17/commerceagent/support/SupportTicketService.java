package com.seventeen17.commerceagent.support;

import com.seventeen17.commerceagent.audit.AuditActorType;
import com.seventeen17.commerceagent.audit.AuditEvent;
import com.seventeen17.commerceagent.audit.AuditWriter;
import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.common.error.ErrorCode;
import com.seventeen17.commerceagent.order.OrderService;
import com.seventeen17.commerceagent.security.CommercePrincipal;
import com.seventeen17.commerceagent.user.UserRole;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Java-authoritative, transactional escalation-ticket creation. */
@Service
public class SupportTicketService {

    private final OrderService orderService;
    private final SupportTicketRepository repository;
    private final AuditWriter auditWriter;

    public SupportTicketService(
            OrderService orderService, SupportTicketRepository repository, AuditWriter auditWriter) {
        this.orderService = orderService;
        this.repository = repository;
        this.auditWriter = auditWriter;
    }

    @Transactional
    public SupportTicketResult create(CommercePrincipal principal, CreateSupportTicketRequest request) {
        if (principal == null || principal.role() != UserRole.CUSTOMER) {
            throw new BusinessException(ErrorCode.ACCESS_DENIED, "Only a customer can create a support ticket");
        }
        String orderId = request.orderId();
        if (orderId != null) {
            if (orderId.isBlank()) {
                throw new BusinessException(ErrorCode.INVALID_PARAMETER, "orderId must be null or nonblank");
            }
            // Reuse the project's sole ownership decision point and its 404 concealment semantics.
            orderService.requireOwnedOrder(principal, orderId);
        }

        SupportTicket ticket = SupportTicket.open(
                UUID.randomUUID().toString(),
                principal.userId(),
                orderId,
                request.category(),
                request.reasonCode(),
                request.evidenceSummary(),
                request.runId().toString());
        repository.saveAndFlush(ticket);

        // REQUIRED joins this transaction: no committed ticket without a committed success audit.
        auditWriter.writeBusinessEvent(new AuditEvent(
                AuditActorType.USER,
                principal.userId(),
                "SUPPORT_TICKET_CREATED",
                "SUPPORT_TICKET",
                ticket.getId(),
                request.runId(),
                "SUCCESS",
                Map.of("category", ticket.getCategory(), "reasonCode", ticket.getReasonCode())));

        return SupportTicketResult.from(ticket);
    }
}
