package com.seventeen17.commerceagent.eligibility;

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
}
