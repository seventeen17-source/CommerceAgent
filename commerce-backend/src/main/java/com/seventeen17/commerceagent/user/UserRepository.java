package com.seventeen17.commerceagent.user;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 * 用户仓储。
 *
 * <p>注意：Customer API 的 ownership 必须从认证 principal 推导，**不允许**接受调用方（更不允许模型）传入任意
 * userId 后直接查询。本仓储只是数据访问能力，权限判断属于 T011。
 */
public interface UserRepository extends JpaRepository<User, String> {

    Optional<User> findByUsername(String username);
}
