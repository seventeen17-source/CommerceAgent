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

    EvalFixtureController(FixtureLoader fixtureLoader) {
        this.fixtureLoader = fixtureLoader;
    }

    @PostMapping("/{caseId}/reset")
    FixtureResetResponse reset(
            @PathVariable String caseId, @RequestBody(required = false) FixtureResetRequest request) {
        String datasetVersion = request == null ? null : request.datasetVersion();
        return fixtureLoader.reset(caseId, datasetVersion);
    }
}
