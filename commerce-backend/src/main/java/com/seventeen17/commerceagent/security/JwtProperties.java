package com.seventeen17.commerceagent.security;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/** 本地 JWT fixture 配置；完整 OAuth/OIDC 身份产品不属于 V1 范围。 */
@ConfigurationProperties(prefix = "commerce.security.jwt")
public record JwtProperties(String secret, String issuer, Duration ttl) {

    public JwtProperties {
        if (secret == null || secret.getBytes(StandardCharsets.UTF_8).length < 32) {
            throw new IllegalArgumentException(
                    "commerce.security.jwt.secret must be at least 32 UTF-8 bytes for HS256");
        }
        if (issuer == null || issuer.isBlank()) {
            throw new IllegalArgumentException("commerce.security.jwt.issuer must not be blank");
        }
        if (ttl == null || ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException("commerce.security.jwt.ttl must be positive");
        }
    }
}
