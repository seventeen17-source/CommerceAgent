package com.seventeen17.commerceagent;

import com.seventeen17.commerceagent.common.error.BusinessException;
import com.seventeen17.commerceagent.common.error.ErrorCode;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ErrorProbeController {

    @GetMapping("/__test/errors/business")
    Map<String, String> businessError() {
        throw new BusinessException(ErrorCode.INVALID_ORDER_STATE);
    }

    @PostMapping("/__test/errors/validation")
    Map<String, String> validation(@Valid @RequestBody ValidationRequest request) {
        return Map.of("value", request.value());
    }

    @GetMapping("/__test/errors/internal")
    Map<String, String> internalError() {
        throw new IllegalStateException("sensitive-internal-message-must-not-leak");
    }

    record ValidationRequest(
            @NotBlank(message = "value must not be blank") String value) {}
}
