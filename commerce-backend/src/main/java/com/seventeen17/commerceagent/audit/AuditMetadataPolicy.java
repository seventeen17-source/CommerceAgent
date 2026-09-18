package com.seventeen17.commerceagent.audit;

import java.lang.reflect.Array;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/** 防止原始凭据和隐藏推理被写入持久化 audit metadata。 */
final class AuditMetadataPolicy {

    private static final Set<String> FORBIDDEN_KEYS = Set.of(
            "authorization",
            "token",
            "rawtoken",
            "accesstoken",
            "refreshtoken",
            "idtoken",
            "password",
            "secret",
            "apikey",
            "cookie",
            "setcookie",
            "chainofthought",
            "cot",
            "reasoning",
            "internalreasoning",
            "rawprompt");

    private static final Pattern JWT_PATTERN =
            Pattern.compile("^[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}$");

    private AuditMetadataPolicy() {}

    static void validate(Map<String, Object> metadata) {
        validateValue(metadata);
    }

    private static void validateValue(Object value) {
        if (value == null) {
            return;
        }
        if (value instanceof Map<?, ?> map) {
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                String key = String.valueOf(entry.getKey());
                if (FORBIDDEN_KEYS.contains(normalizeKey(key))) {
                    throw new IllegalArgumentException("Sensitive audit metadata key is not allowed: " + key);
                }
                validateValue(entry.getValue());
            }
            return;
        }
        if (value instanceof Iterable<?> iterable) {
            for (Object element : iterable) {
                validateValue(element);
            }
            return;
        }
        if (value.getClass().isArray()) {
            for (int index = 0; index < Array.getLength(value); index++) {
                validateValue(Array.get(value, index));
            }
            return;
        }
        if (value instanceof CharSequence sequence) {
            String text = sequence.toString().trim();
            if (text.regionMatches(true, 0, "Bearer ", 0, "Bearer ".length()) || JWT_PATTERN.matcher(text).matches()) {
                throw new IllegalArgumentException("Raw authentication token is not allowed in audit metadata");
            }
        }
    }

    private static String normalizeKey(String key) {
        return key.replaceAll("[^A-Za-z0-9]", "").toLowerCase(java.util.Locale.ROOT);
    }
}
