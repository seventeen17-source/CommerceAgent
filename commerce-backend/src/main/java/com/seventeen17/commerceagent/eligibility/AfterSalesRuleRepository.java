package com.seventeen17.commerceagent.eligibility;

import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 * T010 只暴露规则持久化需要的最小查询。
 *
 * <p>按订单事实选择“当前应命中的规则”属于 T025 EligibilityService，不在 Repository 提前编码业务决策。
 */
public interface AfterSalesRuleRepository extends JpaRepository<AfterSalesRule, Long> {

    Optional<AfterSalesRule> findByRuleCodeAndVersion(String ruleCode, int version);

    boolean existsByRuleCodeAndVersion(String ruleCode, int version);

    /**
     * T020：取全部启用中的规则，交给 {@code EligibilityService} 做确定性筛选。
     *
     * <p>刻意不在 SQL 里按类目/状态/生效窗口过滤：规则集是"小表 + 决策逻辑必须唯一"的组合，把筛选条件拆到
     * JPQL 与 Java 两处，就会出现"数据库筛掉了一条本该参与冲突检测的规则"这类只有线上才看得见的偏差。这里只
     * 用 {@code active} 这一条与决策无关的硬条件减少行数。
     */
    List<AfterSalesRule> findByActiveTrue();
}
