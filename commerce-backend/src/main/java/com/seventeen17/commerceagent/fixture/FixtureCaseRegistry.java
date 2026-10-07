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
            new FixtureCase("refund-logistics-001", DEFAULT_DATASET_VERSION, "t014-refund-logistics-001-v1"),
            // T042: the US2 world. Its defining property is that it is *inside* the return
            // window whenever it is reset -- see FixtureLoader.seedDeliveredReturnCase for why
            // that cannot be expressed with a literal timestamp.
            key("return-delivered-001", DEFAULT_DATASET_VERSION),
            new FixtureCase("return-delivered-001", DEFAULT_DATASET_VERSION, "t042-return-delivered-001-v1"),
            // T048: the US3 world. Two orders whose product summaries both answer to the same clue, so
            // the only correct outcome is a question -- and the case can only prove "nothing was written"
            // if both orders look writable in the first place.
            key("order-ambiguous-001", DEFAULT_DATASET_VERSION),
            new FixtureCase("order-ambiguous-001", DEFAULT_DATASET_VERSION, "t048-order-ambiguous-001-v1"),
            // T048b: the *mirror* of the case above. Three orders are writable in exactly the same
            // way, but only one of them is described by the clue, so the only correct outcome is to
            // resolve that one and finish. Its sibling can only ever return WAITING_USER, which makes
            // "the filter worked" and "the filter did nothing" indistinguishable there.
            key("order-clue-narrow-001", DEFAULT_DATASET_VERSION),
            new FixtureCase("order-clue-narrow-001", DEFAULT_DATASET_VERSION, "t048b-order-clue-narrow-001-v1"));

    Optional<FixtureCase> find(String caseId, String datasetVersion) {
        String resolvedVersion =
                datasetVersion == null || datasetVersion.isBlank() ? DEFAULT_DATASET_VERSION : datasetVersion;
        return Optional.ofNullable(CASES.get(key(caseId, resolvedVersion)));
    }

    private static String key(String caseId, String datasetVersion) {
        return caseId + "::" + datasetVersion;
    }
}
