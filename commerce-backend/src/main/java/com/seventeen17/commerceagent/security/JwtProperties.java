package com.seventeen17.commerceagent.security;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/** Local JWT fixture settings. Full OAuth/OIDC is intentionally outside V1 scope. */
@ConfigurationProperties(prefix = "commerce.security.jwt")
public record JwtProperties(String secret, String issuer, Duration ttl) {

    public JwtProperties {
        if (secret == null || secret.getBytes(StandardCharsets.UTF_8).length < 32) {
            throw new IllegalArgumentException("commerce.security.jwt.secret must be at least 32 UTF-8 bytes for HS256");
        }
        if (issuer == null || issuer.isBlank()) {
            throw new IllegalArgumentException("commerce.security.jwt.issuer must not be blank");
        }
        if (ttl == null || ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException("commerce.security.jwt.ttl must be positive");
        }
    }
}
