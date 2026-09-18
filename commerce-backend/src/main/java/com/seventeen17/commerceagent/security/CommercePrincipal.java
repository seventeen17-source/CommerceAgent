package com.seventeen17.commerceagent.security;

import com.seventeen17.commerceagent.user.UserRole;
import java.io.Serial;
import java.io.Serializable;
import java.security.Principal;

/**
 * 服务端已认证并解析过的当前用户身份。
 *
 * <p>业务代码只能从该 principal 获取当前 userId；不得接受请求参数或模型输出覆盖 ownership。
 */
public record CommercePrincipal(String userId, UserRole role) implements Principal, Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    @Override
    public String getName() {
        return userId;
    }
}
