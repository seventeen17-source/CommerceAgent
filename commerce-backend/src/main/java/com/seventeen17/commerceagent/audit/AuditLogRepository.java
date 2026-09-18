package com.seventeen17.commerceagent.audit;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AuditLogRepository extends JpaRepository<AuditLog, Long> {

    List<AuditLog> findByActionAndResourceIdOrderByCreatedAtAsc(String action, String resourceId);
}
