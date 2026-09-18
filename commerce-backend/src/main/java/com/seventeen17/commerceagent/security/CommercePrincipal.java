package com.seventeen17.commerceagent.security;

import com.seventeen17.commerceagent.user.UserRole;
import java.security.Principal;

/**
 * 服务端已经认证并解析过的当前用户身份。
 *
 * <p>业务代码只能从该 principal 获取当前 userId；不得接受请求参数或模型输出覆盖 ownership。
 */
public record CommercePrincipal(String userId, UserRole role) implements Principal {

    @Override
    public String getName() {
        return userId;
    }
}
