package com.seventeen17.commerceagent.audit;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 结构化业务/安全审计写入器。
 *
 * <p>默认 REQUIRED 事务语义：在现有业务事务中调用时 audit 与业务结果一起提交/回滚，避免留下“业务已成功”的假审计。
 * 需要记录失败/拒绝时，应在失败事实已经确定后单独调用 writer。
 */
@Service
public class AuditWriter {

    private final AuditLogRepository repository;

    public AuditWriter(AuditLogRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public long write(AuditEvent event) {
        AuditMetadataPolicy.validate(event.metadata());
        AuditLog saved = repository.saveAndFlush(AuditLog.from(event));
        return saved.getId();
    }
}
