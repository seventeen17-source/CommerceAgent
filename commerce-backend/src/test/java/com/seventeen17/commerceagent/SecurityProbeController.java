package com.seventeen17.commerceagent;

import com.seventeen17.commerceagent.security.CommercePrincipal;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** 测试专用 HTTP probe，用来证明真正注入业务层的是服务端构建的 principal。 */
@RestController
class SecurityProbeController {

    @GetMapping("/__test/security/principal")
    Map<String, String> principal(@AuthenticationPrincipal CommercePrincipal principal, Authentication authentication) {
        String authority = authentication.getAuthorities().iterator().next().getAuthority();
        return Map.of(
                "userId", principal.userId(),
                "role", principal.role().name(),
                "authority", authority);
    }
}
