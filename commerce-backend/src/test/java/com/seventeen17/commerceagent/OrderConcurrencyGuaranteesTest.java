package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.seventeen17.commerceagent.logistics.Shipment;
import com.seventeen17.commerceagent.logistics.ShipmentRepository;
import com.seventeen17.commerceagent.logistics.ShipmentStatus;
import com.seventeen17.commerceagent.order.Order;
import com.seventeen17.commerceagent.order.OrderRepository;
import com.seventeen17.commerceagent.order.OrderStatus;
import com.seventeen17.commerceagent.user.User;
import com.seventeen17.commerceagent.user.UserRepository;
import com.seventeen17.commerceagent.user.UserRole;
import java.math.BigDecimal;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.test.context.ActiveProfiles;

/**
 * 持久层并发保证的**可执行证明**（T009 交付物的一部分）。
 *
 * <p>本测试刻意不标注 {@code @Transactional}：每一次仓储调用都必须跑在**自己的事务**里，这样才能构造出"两个读者
 * 基于同一份快照，其中一个先写入成功"的场景。若整个测试方法共用一个事务，两个读者会落到同一个持久化上下文，也就
 * 测不出并发语义了。
 *
 * <p>它编码了本项目最关键的一组区分（见 docs/devlog 的 T009 面试知识点）：
 *
 * <ul>
 *   <li><b>乐观锁管"更新冲突"</b>：{@link #staleUpdateIsRejectedByOptimisticLocking()} 验证订单；
 *       {@link #staleShipmentUpdateIsRejectedByOptimisticLocking()} 验证物流。基于过期快照的写入必须被拒绝，而不是静默覆盖。
 *   <li><b>唯一约束管"重复创建"</b>：{@link #duplicateShipmentForSameOrderIsRejectedByUniqueConstraint()} —— 两条
 *       新记录的乐观锁版本号都是一样的初始值，`@Version` 在这里毫无作用；拦住重复的是数据库 UNIQUE 约束。
 * </ul>
 */
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class OrderConcurrencyGuaranteesTest {

    private static final String USER_ID = "t009-user-1";
    private static final String USERNAME = "t009-customer";

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private ShipmentRepository shipmentRepository;

    @Test
    void staleUpdateIsRejectedByOptimisticLocking() {
        String orderId = "t009-order-lock";
        seedOrder(orderId);

        // 两次独立读取 = 两个"读者"各自拿到同一份快照。
        // 用两个不同的事务很重要：同一个持久化上下文里 Hibernate 会返回同一个实例，测不出任何并发语义。
        Order firstReader = orderRepository.findById(orderId).orElseThrow();
        Order secondReader = orderRepository.findById(orderId).orElseThrow();
        Long snapshotVersion = firstReader.getVersion();
        assertEquals(snapshotVersion, secondReader.getVersion(), "两个读者应看到同一个版本号");

        // 第一个读者先写入成功
        firstReader.setStatus(OrderStatus.CANCELLED);
        orderRepository.save(firstReader);

        Order afterFirstWrite = orderRepository.findById(orderId).orElseThrow();
        assertEquals(snapshotVersion + 1, afterFirstWrite.getVersion(), "写入成功后版本号必须自增");
        assertEquals(OrderStatus.CANCELLED, afterFirstWrite.getStatus());

        // 第二个读者拿着过期快照写入 —— 必须失败，而不是把第一个人的结果覆盖掉
        secondReader.setStatus(OrderStatus.CLOSED);
        assertThrows(
                ObjectOptimisticLockingFailureException.class,
                () -> orderRepository.save(secondReader),
                "基于过期快照的写入必须被拒绝");

        // 并且第一个读者的结果确实没有被覆盖
        assertEquals(
                OrderStatus.CANCELLED,
                orderRepository.findById(orderId).orElseThrow().getStatus(),
                "先写入的结果不能被后写入者覆盖：这正是丢失更新要防的事");
    }


    @Test
    void staleShipmentUpdateIsRejectedByOptimisticLocking() {
        String orderId = "t009-order-shipment-lock";
        String shipmentId = "t009-shipment-lock";
        seedOrder(orderId);
        shipmentRepository.save(
                Shipment.create(shipmentId, orderId, "SF", "SF-LOCK-0001", ShipmentStatus.CREATED));

        Shipment firstReader = shipmentRepository.findById(shipmentId).orElseThrow();
        Shipment secondReader = shipmentRepository.findById(shipmentId).orElseThrow();
        Long snapshotVersion = firstReader.getVersion();
        assertEquals(snapshotVersion, secondReader.getVersion(), "两个物流读者应看到同一个版本号");

        Instant firstEventAt = Instant.parse("2026-09-18T06:00:00Z");
        firstReader.setStatus(ShipmentStatus.IN_TRANSIT);
        firstReader.setLastEventAt(firstEventAt);
        shipmentRepository.save(firstReader);

        Shipment afterFirstWrite = shipmentRepository.findById(shipmentId).orElseThrow();
        assertEquals(snapshotVersion + 1, afterFirstWrite.getVersion(), "物流写入成功后版本号必须自增");
        assertEquals(ShipmentStatus.IN_TRANSIT, afterFirstWrite.getStatus());
        assertEquals(firstEventAt, afterFirstWrite.getLastEventAt());

        secondReader.setStatus(ShipmentStatus.DELIVERED);
        assertThrows(
                ObjectOptimisticLockingFailureException.class,
                () -> shipmentRepository.save(secondReader),
                "基于过期物流快照的写入必须被拒绝");

        Shipment current = shipmentRepository.findById(shipmentId).orElseThrow();
        assertEquals(ShipmentStatus.IN_TRANSIT, current.getStatus(), "先写入的物流状态不能被过期快照覆盖");
        assertEquals(firstEventAt, current.getLastEventAt(), "先写入的物流时间也不能被过期快照覆盖");
    }

    @Test
    void duplicateShipmentForSameOrderIsRejectedByUniqueConstraint() {
        String orderId = "t009-order-dup";
        seedOrder(orderId);

        // 第一条：正常落库。注意两条运单的乐观锁版本号都是一样的初始值。
        Shipment first = Shipment.create("t009-ship-1", orderId, "SF", "SF-0001", ShipmentStatus.CREATED);
        shipmentRepository.save(first);

        // 第二条：id 不同、运单号不同，唯一"重复"的是 order_id。
        // 这里 @Version 完全帮不上忙（两条都是新记录，没有任何共同的版本号可比），
        // 拦住它的是 V001 里 shipments.order_id 的 UNIQUE 约束。
        Shipment second = Shipment.create("t009-ship-2", orderId, "SF", "SF-0002", ShipmentStatus.CREATED);
        assertThrows(
                DataIntegrityViolationException.class, () -> shipmentRepository.save(second), "同一订单的第二条运单必须被数据库唯一约束拒绝");

        assertTrue(shipmentRepository.existsByOrderId(orderId), "第一条运单应仍然存在");
        assertEquals(1, shipmentRepository.findByOrderId(orderId).stream().count(), "该订单只能有一条运单");
    }

    private void seedOrder(String orderId) {
        if (userRepository.findById(USER_ID).isEmpty()) {
            userRepository.save(User.create(USER_ID, USERNAME, UserRole.CUSTOMER));
        }
        orderRepository.save(Order.create(orderId, USER_ID, OrderStatus.SHIPPED, new BigDecimal("299.00"), "CNY"));
    }
}
