package com.seventeen17.commerceagent.logistics;

/**
 * 物流状态（Java 侧枚举）。
 *
 * <p><b>重要：这不是数据库完整性约束。</b> `commerce.shipments.status` 列在 V001 中**没有** CHECK 约束，
 * 数据库仍会接受任意字符串。本枚举只保证"经过 Java 代码写入时不会写错"，它挡不住手工 SQL、另一套服务或批量导入。
 *
 * <p>这正是 Java 枚举与数据库约束的差别：枚举是**代码里的规则**（只管得住走这段代码的路径），CHECK/UNIQUE
 * 才是**数据本身的规则**（谁都绕不过）。若要真正强制，需要后续 Flyway 迁移补一个 CHECK 约束。
 *
 * <p>取值集合为 V1 最小集，待 T024（物流停滞判定）确定完整状态机后再扩展。
 */
public enum ShipmentStatus {
    /** 运单已创建，尚无有效物流轨迹。 */
    CREATED,
    /** 运输中。 */
    IN_TRANSIT,
    /** 已签收 —— 决定走退款路径还是退货路径的关键状态。 */
    DELIVERED
}
