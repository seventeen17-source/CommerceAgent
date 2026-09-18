package com.seventeen17.commerceagent.logistics;

import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 * 物流事件仓储。
 *
 * <p>两个方法都按 `occurred_at DESC` 排序：停滞时长判定只关心"最近一次有效事件发生在什么时候"，所以提供
 * 直接取最近一条的能力，而不是让调用方先加载全部事件再自己排序。
 */
public interface LogisticsEventRepository extends JpaRepository<LogisticsEvent, Long> {

    List<LogisticsEvent> findByShipment_IdOrderByOccurredAtDesc(String shipmentId);

    Optional<LogisticsEvent> findFirstByShipment_IdOrderByOccurredAtDesc(String shipmentId);
}
