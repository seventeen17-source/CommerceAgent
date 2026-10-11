package com.seventeen17.commerceagent.support;

/** Authority-owned identity and lifecycle state returned after a committed create. */
public record SupportTicketResult(String ticketId, SupportTicketStatus status) {
    public static SupportTicketResult from(SupportTicket ticket) {
        return new SupportTicketResult(ticket.getId(), ticket.getStatus());
    }
}
