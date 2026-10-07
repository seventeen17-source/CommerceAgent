package com.seventeen17.commerceagent.user;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import org.hibernate.annotations.Generated;
import org.hibernate.generator.EventType;

/**
 * `commerce.users` —— 认证主体，也是所有权（ownership）判定的来源。
 *
 * <p>本实体只做持久化映射，不含任何认证或授权逻辑：认证/授权属 T011 的 `security/`。
 *
 * <p>映射说明：
 *
 * <ul>
 *   <li>`id` 由应用分配（fixture 用 `customer-001` 这类稳定可读的 id），不用数据库自增，因此没有
 *       `@GeneratedValue`。
 *   <li>`created_at` 声明为 `insertable/updatable = false`：时间戳的权威在数据库（V001 里有
 *       `DEFAULT CURRENT_TIMESTAMP`），并用 Hibernate `@Generated(INSERT)` 在 INSERT 后把数据库生成值
 *       同步回 managed entity。注意本实体是应用分配 id 且没有 `@Version`，调用仓储保存时应使用 `save*()` 的返回值。
 *   <li>表名不带 schema：`spring.jpa.properties.hibernate.default_schema = commerce` 已统一指定
 *       （见 T007 的 application.yml）。
 * </ul>
 */
@Entity
@Table(name = "users")
public class User {

    @Id
    @Column(name = "id", length = 64, nullable = false, updatable = false)
    private String id;

    /** 登录标识；数据库上有 UNIQUE，重复用户名必须在数据库层被拒绝。 */
    @Column(name = "username", length = 100, nullable = false)
    private String username;

    @Enumerated(EnumType.STRING)
    @Column(name = "role", length = 20, nullable = false)
    private UserRole role;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", length = 20, nullable = false)
    private UserStatus status;

    @Generated(event = EventType.INSERT)
    @Column(name = "created_at", nullable = false, insertable = false, updatable = false)
    private Instant createdAt;

    /** JPA 要求的无参构造器；业务代码请用下面的工厂方法。 */
    protected User() {}

    public static User create(String id, String username, UserRole role) {
        User user = new User();
        user.id = id;
        user.username = username;
        user.role = role;
        user.status = UserStatus.ACTIVE;
        return user;
    }

    public String getId() {
        return id;
    }

    public String getUsername() {
        return username;
    }

    public UserRole getRole() {
        return role;
    }

    public void setRole(UserRole role) {
        this.role = role;
    }

    public UserStatus getStatus() {
        return status;
    }

    public void setStatus(UserStatus status) {
        this.status = status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
