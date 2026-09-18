package com.seventeen17.commerceagent.security;

import com.seventeen17.commerceagent.user.User;
import com.seventeen17.commerceagent.user.UserRepository;
import com.seventeen17.commerceagent.user.UserStatus;
import java.util.List;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.AbstractOAuth2TokenAuthenticationToken;
import org.springframework.stereotype.Component;

/**
 * JWT -> role-aware principal。
 *
 * <p>JwtDecoder 先验证签名、issuer 与时间；这里只把已验证的 {@code sub} 当身份索引，再从权威
 * {@code commerce.users} 读取当前 status/role。token 中即使额外塞入 {@code role} claim，也不会成为授权来源。
 */
@Component
public class CommerceJwtAuthenticationConverter implements Converter<Jwt, AbstractOAuth2TokenAuthenticationToken<Jwt>> {

    private final UserRepository userRepository;

    public CommerceJwtAuthenticationConverter(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @Override
    public AbstractOAuth2TokenAuthenticationToken<Jwt> convert(Jwt jwt) {
        String userId = jwt.getSubject();
        if (userId == null || userId.isBlank()) {
            throw new BadCredentialsException("JWT subject is required");
        }

        User user = userRepository
                .findById(userId)
                .orElseThrow(() -> new BadCredentialsException("JWT subject does not map to a known user"));
        if (user.getStatus() != UserStatus.ACTIVE) {
            throw new BadCredentialsException("User is not active");
        }

        CommercePrincipal principal = new CommercePrincipal(user.getId(), user.getRole());
        SimpleGrantedAuthority authority =
                new SimpleGrantedAuthority("ROLE_" + user.getRole().name());
        return new CommerceJwtAuthenticationToken(jwt, principal, List.of(authority));
    }
}
