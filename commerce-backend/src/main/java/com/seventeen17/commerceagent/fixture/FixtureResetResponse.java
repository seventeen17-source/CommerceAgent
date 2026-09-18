package com.seventeen17.commerceagent.fixture;

import java.time.Instant;

public record FixtureResetResponse(
        String caseId, String datasetVersion, String fixtureVersion, Instant resetAt) {}
