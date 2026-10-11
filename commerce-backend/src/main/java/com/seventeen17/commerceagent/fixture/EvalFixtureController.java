package com.seventeen17.commerceagent.fixture;

import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/eval/fixtures")
@Profile({"test", "eval"})
class EvalFixtureController {

    private final FixtureLoader fixtureLoader;
    private final EvalFaultInjection faults;

    EvalFixtureController(FixtureLoader fixtureLoader, EvalFaultInjection faults) {
        this.fixtureLoader = fixtureLoader;
        this.faults = faults;
    }

    @PostMapping("/{caseId}/reset")
    FixtureResetResponse reset(
            @PathVariable String caseId, @RequestBody(required = false) FixtureResetRequest request) {
        String datasetVersion = request == null ? null : request.datasetVersion();
        // T063-live: the fault belongs to the world, so it is decided by the same call that builds
        // the world. Clear *before* resetting so a failing reset leaves a world with no injection
        // rather than the previous case's fault still armed -- an eval run must never inherit a
        // failure it did not ask for.
        faults.clear();
        FixtureResetResponse response = fixtureLoader.reset(caseId, datasetVersion);
        faults.applyForCase(caseId);
        return response;
    }
}
