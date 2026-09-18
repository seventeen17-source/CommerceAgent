package com.seventeen17.commerceagent.security;

import com.seventeen17.commerceagent.user.UserRole;
import java.security.Principal;

/** Server-authenticated identity exposed to business code. */
public record CommercePrincipal(String userId, UserRole role) implements Principal {

    @Override
    public String getName() {
        return userId;
    }
}
