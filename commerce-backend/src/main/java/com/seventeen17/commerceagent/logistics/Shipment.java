package com.seventeen17.commerceagent.logistics;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.time.Instant;

/**
 * `commerce.shipments` —— 物流主记录。
 *
 * <p>三个映射要点：
 *
 * <ul>
 *   <li><b>关系方向是 OneToOne，不是 OneToMany</b>：V001 里 `order_id` 是 UNIQUE，V1 契约为"一个订单最多一个
 *       包裹"。若顺手写成 `@OneToMany`，编译与启动检查都不会报错，但语义已经错了 —— 数据库约束管得住数据，
 *       管不住映射方向。
 *   <li><b>刻意不在 {@code Order} 上放反向引用</b>：`order` 包不需要依赖 `logistics` 包，读订单时也不该顺带加载物流。
 *       需要物流信息时通过 {@link ShipmentRepository#findByOrder_Id} 查。聚合边界画在这里。
 *   <li>有 `version` 列，因此做乐观锁：物流状态同样会被"读取后并发修改"。
 * </ul>
 */
@Entity
@Table(name = "shipments")
public class Shipment {

    @Id
    @Column(name = "id", length = 64, nullable = false, updatable = false)
    private String id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false, updatable = false)
    private OrderRef order;

    @Column(name = "carrier", length = 100, nullable = false)
    private String carrier;

    @Column(name = "tracking_number", length = 128, nullable = false)
    private String trackingNumber;

    /**
     * 物流状态。
     *
     * <p>注意：数据库该列**没有** CHECK 约束，枚举只是 Java 侧护栏，不是完整性保证（详见
     * {@link ShipmentStatus} 的说明）。数据库确实强制的是"同一 (carrier, tracking_number) 不能重复出现"，
     * 那条由 V001 的 UNIQUE 约束保证，不需要在实体上重复声明。
     */
    @Enumerated(EnumType.STRING)
    @Column(name = "status", length = 32, nullable = false)
    private ShipmentStatus status;

    /** 最近一次有效物流事件时间 —— "物流停滞时长"的权威计算基准。 */
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
        shipment.order = new OrderRef(orderId);
        shipment.carrier = carrier;
        shipment.trackingNumber = trackingNumber;
        shipment.status = status;
        return shipment;
    }

    public String getId() {
        return id;
    }

    public String getOrderId() {
        return order == null ? null : order.getId();
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
