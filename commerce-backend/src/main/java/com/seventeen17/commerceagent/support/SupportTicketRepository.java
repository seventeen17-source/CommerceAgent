package com.seventeen17.commerceagent.support;

import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 * Owner-scoped reads for SupportTicket.
 *
 * <p>The repository deliberately has no cross-owner lookup helper for customer paths. T060 may
 * create tickets only after ownership has been established; later customer reads should use these
 * owner-scoped methods rather than load-then-authorize.
 */
public interface SupportTicketRepository extends JpaRepository<SupportTicket, String> {

    Optional<SupportTicket> findByIdAndUserId(String id, String userId);

    List<SupportTicket> findByUserIdOrderByCreatedAtDesc(String userId);

    List<SupportTicket> findByRunIdAndUserIdOrderByCreatedAtAsc(String runId, String userId);
}
