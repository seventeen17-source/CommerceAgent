package com.seventeen17.commerceagent.security;

import java.util.Collection;
import java.util.Map;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.AbstractOAuth2TokenAuthenticationToken;

/** Spring Security Authentication：token 保留 Jwt，业务 principal 则收敛为 {@link CommercePrincipal}。 */
final class CommerceJwtAuthenticationToken extends AbstractOAuth2TokenAuthenticationToken<Jwt> {

    private final CommercePrincipal principal;

    CommerceJwtAuthenticationToken(
            Jwt jwt, CommercePrincipal principal, Collection<? extends GrantedAuthority> authorities) {
        super(jwt, authorities);
        this.principal = principal;
        setAuthenticated(true);
    }

    @Override
    public Object getCredentials() {
        return "";
    }

    @Override
    public CommercePrincipal getPrincipal() {
        return principal;
    }

    @Override
    public String getName() {
        return principal.userId();
    }

    @Override
    public Map<String, Object> getTokenAttributes() {
        return getToken().getClaims();
    }
}
