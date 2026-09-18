package com.seventeen17.commerceagent.fixture;

import java.util.Map;
import java.util.Optional;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile({"dev", "test", "eval"})
class FixtureCaseRegistry {

    private static final String DEFAULT_DATASET_VERSION = "v1";
    private static final Map<String, FixtureCase> CASES = Map.of(
            key("refund-logistics-001", DEFAULT_DATASET_VERSION),
            new FixtureCase("refund-logistics-001", DEFAULT_DATASET_VERSION, "t014-refund-logistics-001-v1"));

    Optional<FixtureCase> find(String caseId, String datasetVersion) {
        String resolvedVersion =
                datasetVersion == null || datasetVersion.isBlank() ? DEFAULT_DATASET_VERSION : datasetVersion;
        return Optional.ofNullable(CASES.get(key(caseId, resolvedVersion)));
    }

    private static String key(String caseId, String datasetVersion) {
        return caseId + "::" + datasetVersion;
    }
}
