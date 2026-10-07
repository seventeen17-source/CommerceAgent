package com.seventeen17.commerceagent.logistics;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.time.Instant;

/**
 * `commerce.shipments` —— 物流主记录。
 *
 * <p>三个映射要点：
 *
 * <ul>
 *   <li><b>订单引用直接保存不可变 id</b>：`order_id` 映射为普通 String，而不是再为 `orders` 表创建第二个轻量实体。
 *       V001 的 FOREIGN KEY 保证订单存在，UNIQUE 保证 V1 的“一个订单最多一个包裹”；JPA 不需要重复表达这两个数据库事实。
 *   <li><b>刻意不在 {@code Order} 上放物流反向引用</b>：`order` 包不依赖 `logistics` 包，物流包也不依赖订单实体。
 *       需要物流信息时通过 {@link ShipmentRepository#findByOrderId} 查，避免重复映射同一张 `orders` 表。
 *   <li>有 `version` 列，因此做乐观锁：物流状态同样会被“读取后并发修改”。
 * </ul>
 */
@Entity
@Table(name = "shipments")
public class Shipment {

    @Id
    @Column(name = "id", length = 64, nullable = false, updatable = false)
    private String id;

    /** 订单外键值不可变；引用完整性与 0/1 基数由 V001 的 FK + UNIQUE 在数据库层强制。 */
    @Column(name = "order_id", length = 64, nullable = false, updatable = false)
    private String orderId;

    @Column(name = "carrier", length = 100, nullable = false)
    private String carrier;

    @Column(name = "tracking_number", length = 128, nullable = false)
    private String trackingNumber;

    /**
     * 物流状态。
     *
     * <p>注意：数据库该列<b>没有</b> CHECK 约束，枚举只是 Java 侧护栏，不是完整性保证（详见
     * {@link ShipmentStatus} 的说明）。数据库确实强制的是“同一 (carrier, tracking_number) 不能重复出现”，
     * 那条由 V001 的 UNIQUE 约束保证，不需要在实体上重复声明。
     */
    @Enumerated(EnumType.STRING)
    @Column(name = "status", length = 32, nullable = false)
    private ShipmentStatus status;

    /** 最近一次有效物流事件时间 —— “物流停滞时长”的权威计算基准。 */
    @Column(name = "last_event_at")
    private Instant lastEventAt;

    /** 签收时间；是否签收决定走退款还是退货路径。 */
    @Column(name = "signed_at")
    private Instant signedAt;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    protected Shipment() {}

    public static Shipment create(
            String id, String orderId, String carrier, String trackingNumber, ShipmentStatus status) {
        Shipment shipment = new Shipment();
        shipment.id = id;
        shipment.orderId = orderId;
        shipment.carrier = carrier;
        shipment.trackingNumber = trackingNumber;
        shipment.status = status;
        return shipment;
    }

    public String getId() {
        return id;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getCarrier() {
        return carrier;
    }

    public String getTrackingNumber() {
        return trackingNumber;
    }

    public ShipmentStatus getStatus() {
        return status;
    }

    public void setStatus(ShipmentStatus status) {
        this.status = status;
    }

    public Instant getLastEventAt() {
        return lastEventAt;
    }

    public void setLastEventAt(Instant lastEventAt) {
        this.lastEventAt = lastEventAt;
    }

    public Instant getSignedAt() {
        return signedAt;
    }

    public void setSignedAt(Instant signedAt) {
        this.signedAt = signedAt;
    }

    public Long getVersion() {
        return version;
    }
}
