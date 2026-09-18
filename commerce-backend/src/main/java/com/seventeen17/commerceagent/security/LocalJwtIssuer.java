package com.seventeen17.commerceagent.security;

import java.time.Instant;
import org.springframework.context.annotation.Profile;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.stereotype.Component;

/** 本地 fixture token 签发器，不是登录接口。 */
@Component
@Profile({"dev", "test", "eval"})
public class LocalJwtIssuer {

    private final JwtEncoder encoder;
    private final JwtProperties properties;

    public LocalJwtIssuer(JwtEncoder encoder, JwtProperties properties) {
        this.encoder = encoder;
        this.properties = properties;
    }

    public String issue(String userId) {
        if (userId == null || userId.isBlank()) {
            throw new IllegalArgumentException("userId must not be blank");
        }

        Instant now = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
                .issuer(properties.issuer())
                .subject(userId)
                .issuedAt(now)
                .expiresAt(now.plus(properties.ttl()))
                .build();
        return encoder.encode(JwtEncoderParameters.from(claims)).getTokenValue();
    }
}
