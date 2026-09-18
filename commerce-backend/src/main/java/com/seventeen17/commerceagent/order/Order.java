package com.seventeen17.commerceagent.order;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.OrderBy;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.hibernate.annotations.Generated;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.generator.EventType;
import org.hibernate.type.SqlTypes;

/**
 * `commerce.orders` —— 权威订单状态，本项目所有业务判断的基础。
 *
 * <p>本实体只做持久化映射，不含任何状态迁移规则；合法迁移必须在服务层确定性校验后执行（T019+）。
 *
 * <p>三个关键设计点：
 *
 * <ul>
 *   <li><b>所有权不可变</b>：{@code ownerId} 映射为 `updatable = false`。这意味着 Hibernate 永远不会把它写进
 *       UPDATE 语句 —— 订单一旦创建，归属就改不了。"Order ownership 不可由模型指定"这条宪法约束因此不只停留在
 *       口头上，而是被映射层强制。
 *   <li><b>乐观锁</b>：{@code version} 上标注 {@code @Version}，Hibernate 会在每次 UPDATE 时自动补上
 *       `AND version = ?`，受影响行数为 0 时抛 {@code ObjectOptimisticLockingFailureException}。它只防"已有的
 *       这一行被并发覆盖"，不防"重复插入" —— 后者要靠唯一约束。
 *   <li><b>类型必须如实映射</b>：{@code currency} 在 V001 里是 `CHAR(3)`（定长，ISO 4217 货币代码）。Hibernate
 *       默认把 String 当作 `varchar`，`ddl-auto: validate` 会因此启动失败，所以显式声明
 *       {@code @JdbcTypeCode(SqlTypes.CHAR)} 告诉它真实类型。绝不能反过来去改已执行过的 V001 —— 那会让
 *       Flyway 的 checksum 校验失败。
 * </ul>
 */
@Entity
@Table(name = "orders")
public class Order {

    @Id
    @Column(name = "id", length = 64, nullable = false, updatable = false)
    private String id;

    /**
     * 订单归属。刻意映射为普通列而不是 {@code @ManyToOne User}：这样既让"不可变"表达得更直接，又让
     * ownership-scoped 查询（{@code findByIdAndOwnerId}）保持自然写法，同时避免为取一个 id 而加载用户实体。
     */
    @Column(name = "user_id", length = 64, nullable = false, updatable = false)
    private String ownerId;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", length = 20, nullable = false)
    private OrderStatus status;

    @Column(name = "total_amount", precision = 19, scale = 2, nullable = false)
    private BigDecimal totalAmount;

    /** V001 中的类型是 `CHAR(3)`（定长），必须显式声明，否则 validate 会报类型不匹配。 */
    @JdbcTypeCode(SqlTypes.CHAR)
    @Column(name = "currency", length = 3, nullable = false)
    private String currency;

    /** 数据库 DEFAULT CURRENT_TIMESTAMP 生成；@Generated 让 INSERT 后的实体立即拿到数据库权威值。 */
    @Generated(event = EventType.INSERT)
    @Column(name = "created_at", nullable = false, insertable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "shipped_at")
    private Instant shippedAt;

    @Column(name = "delivered_at")
    private Instant deliveredAt;

    /**
     * 售后状态。可空，`null` 表示尚无售后动作。
     *
     * <p>注意：数据库该列**没有** CHECK 约束，枚举值集合也只是 V1 最小集（见 {@link AfterSalesStatus}）。
     * 枚举是 Java 侧护栏，不是数据库完整性保证 —— 手工 SQL 仍可写入任意字符串。
     */
    @Enumerated(EnumType.STRING)
    @Column(name = "after_sales_status", length = 32)
    private AfterSalesStatus afterSalesStatus;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL, orphanRemoval = true, fetch = FetchType.LAZY)
    @OrderBy("id ASC")
    private List<OrderItem> items = new ArrayList<>();

    /** JPA 要求的无参构造器；业务代码请用下面的工厂方法。 */
    protected Order() {}

    public static Order create(String id, String ownerId, OrderStatus status, BigDecimal totalAmount, String currency) {
        Order order = new Order();
        order.id = id;
        order.ownerId = ownerId;
        order.status = status;
        order.totalAmount = totalAmount;
        order.currency = currency;
        return order;
    }

    /**
     * 双向关系必须由聚合根维护两侧，否则内存里的对象图和数据库会不一致（经典 JPA 陷阱）。
     */
    public void addItem(OrderItem item) {
        items.add(item);
        item.assignTo(this);
    }

    public void removeItem(OrderItem item) {
        items.remove(item);
        item.assignTo(null);
    }

    public String getId() {
        return id;
    }

    public String getOwnerId() {
        return ownerId;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public String getCurrency() {
        return currency;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getShippedAt() {
        return shippedAt;
    }

    public void setShippedAt(Instant shippedAt) {
        this.shippedAt = shippedAt;
    }

    public Instant getDeliveredAt() {
        return deliveredAt;
    }

    public void setDeliveredAt(Instant deliveredAt) {
        this.deliveredAt = deliveredAt;
    }

    public AfterSalesStatus getAfterSalesStatus() {
        return afterSalesStatus;
    }

    public void setAfterSalesStatus(AfterSalesStatus afterSalesStatus) {
        this.afterSalesStatus = afterSalesStatus;
    }

    /** 乐观锁版本号。只读暴露：写入由 Hibernate 负责，业务代码不得手动改。 */
    public Long getVersion() {
        return version;
    }

    /** 返回只读视图，避免外部绕过聚合根的 addItem/removeItem 破坏双向一致性。 */
    public List<OrderItem> getItems() {
        return Collections.unmodifiableList(items);
    }
}
