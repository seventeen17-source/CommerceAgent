package com.seventeen17.commerceagent;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.seventeen17.commerceagent.security.JwtProperties;
import com.seventeen17.commerceagent.security.LocalJwtIssuer;
import com.seventeen17.commerceagent.user.User;
import com.seventeen17.commerceagent.user.UserRepository;
import com.seventeen17.commerceagent.user.UserRole;
import com.seventeen17.commerceagent.user.UserStatus;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

/** T011：真实 Bearer JWT -> Spring Security -> role-aware CommercePrincipal 的集成证明。 */
@ActiveProfiles("test")
@Import({TestcontainersConfiguration.class, SecurityProbeController.class})
@SpringBootTest
@AutoConfigureMockMvc
class JwtSecurityIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private LocalJwtIssuer localJwtIssuer;

    @Autowired
    private JwtEncoder jwtEncoder;

    @Autowired
    private JwtProperties jwtProperties;

    @Test
    void validJwtBuildsPrincipalFromAuthoritativeUserRecord() throws Exception {
        seedUser("t011-customer-valid", "t011-customer-valid", UserRole.CUSTOMER, UserStatus.ACTIVE);
        String token = localJwtIssuer.issue("t011-customer-valid");

        mockMvc.perform(get("/__test/security/principal").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.userId").value("t011-customer-valid"))
                .andExpect(jsonPath("$.role").value("CUSTOMER"))
                .andExpect(jsonPath("$.authority").value("ROLE_CUSTOMER"));
    }

    @Test
    void requestWithoutJwtIsRejected() throws Exception {
        mockMvc.perform(get("/__test/security/principal")).andExpect(status().isUnauthorized());
    }

    @Test
    void tamperedJwtSignatureIsRejected() throws Exception {
        seedUser("t011-customer-tampered", "t011-customer-tampered", UserRole.CUSTOMER, UserStatus.ACTIVE);
        String token = localJwtIssuer.issue("t011-customer-tampered");
        char replacement = token.charAt(token.length() - 1) == 'A' ? 'B' : 'A';
        String tampered = token.substring(0, token.length() - 1) + replacement;

        mockMvc.perform(get("/__test/security/principal").header("Authorization", "Bearer " + tampered))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void expiredJwtIsRejected() throws Exception {
        seedUser("t011-customer-expired", "t011-customer-expired", UserRole.CUSTOMER, UserStatus.ACTIVE);
        Instant now = Instant.now();
        String token = encode("t011-customer-expired", now.minusSeconds(1200), now.minusSeconds(600), null);

        mockMvc.perform(get("/__test/security/principal").header("Authorization", "Bearer " + token))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void jwtRoleClaimCannotOverrideAuthoritativeDatabaseRole() throws Exception {
        seedUser("t011-customer-role", "t011-customer-role", UserRole.CUSTOMER, UserStatus.ACTIVE);
        Instant now = Instant.now();
        String token = encode("t011-customer-role", now, now.plusSeconds(3600), "APPROVER");

        mockMvc.perform(get("/__test/security/principal").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role").value("CUSTOMER"))
                .andExpect(jsonPath("$.authority").value("ROLE_CUSTOMER"));
    }

    @Test
    void disabledUserIsRejectedEvenWhenJwtSignatureIsValid() throws Exception {
        seedUser("t011-customer-disabled", "t011-customer-disabled", UserRole.CUSTOMER, UserStatus.DISABLED);
        String token = localJwtIssuer.issue("t011-customer-disabled");

        mockMvc.perform(get("/__test/security/principal").header("Authorization", "Bearer " + token))
                .andExpect(status().isUnauthorized());
    }

    private String encode(String subject, Instant issuedAt, Instant expiresAt, String roleClaim) {
        JwtClaimsSet.Builder builder = JwtClaimsSet.builder()
                .issuer(jwtProperties.issuer())
                .subject(subject)
                .issuedAt(issuedAt)
                .expiresAt(expiresAt);
        if (roleClaim != null) {
            builder.claim("role", roleClaim);
        }
        return jwtEncoder.encode(JwtEncoderParameters.from(builder.build())).getTokenValue();
    }

    private void seedUser(String id, String username, UserRole role, UserStatus status) {
        User user = User.create(id, username, role);
        user.setStatus(status);
        userRepository.saveAndFlush(user);
    }
}
