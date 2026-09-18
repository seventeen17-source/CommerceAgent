package com.seventeen17.commerceagent.audit;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 结构化业务/安全审计写入器。
 *
 * <p>业务成功型事件使用 REQUIRED：审计与关键业务写入一起提交/回滚，防止业务回滚后留下假 SUCCESS。
 *
 * <p>安全拒绝/失败事件使用 REQUIRES_NEW：外层业务事务即使回滚，已经确定发生的安全事件仍可独立提交。
 */
@Service
public class AuditWriter {

    private final AuditLogRepository repository;

    public AuditWriter(AuditLogRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public long writeBusinessEvent(AuditEvent event) {
        return persist(event);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public long writeSecurityEvent(AuditEvent event) {
        return persist(event);
    }

    private long persist(AuditEvent event) {
        AuditMetadataPolicy.validate(event.metadata());
        AuditLog saved = repository.saveAndFlush(AuditLog.from(event));
        return saved.getId();
    }
}
