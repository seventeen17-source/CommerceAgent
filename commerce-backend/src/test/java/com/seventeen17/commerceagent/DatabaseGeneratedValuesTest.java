package com.seventeen17.commerceagent;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import com.seventeen17.commerceagent.order.Order;
import com.seventeen17.commerceagent.order.OrderRepository;
import com.seventeen17.commerceagent.order.OrderStatus;
import com.seventeen17.commerceagent.user.User;
import com.seventeen17.commerceagent.user.UserRepository;
import com.seventeen17.commerceagent.user.UserRole;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

/** 验证数据库生成字段在 INSERT 后会同步回实体，而不是只存在于数据库行中。 */
@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class DatabaseGeneratedValuesTest {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void createdAtIsAvailableImmediatelyAfterDatabaseGeneratedInsert() {
        User user = User.create("t009-generated-user", "t009-generated-customer", UserRole.CUSTOMER);
        User savedUser = userRepository.saveAndFlush(user);
        assertNotNull(savedUser.getCreatedAt(), "User.createdAt 应在 INSERT 后从数据库回填到 saveAndFlush 返回的实体");

        Order order = Order.create(
                "t009-generated-order", savedUser.getId(), OrderStatus.PAID, new BigDecimal("19.90"), "CNY");
        orderRepository.saveAndFlush(order);
        assertNotNull(order.getCreatedAt(), "Order.createdAt 应在 INSERT 后回填到当前 Order 实例");
    }
}
