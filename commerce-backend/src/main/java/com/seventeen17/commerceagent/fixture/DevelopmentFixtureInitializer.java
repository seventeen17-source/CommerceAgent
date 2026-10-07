package com.seventeen17.commerceagent.fixture;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Profile("dev")
@Order(Ordered.LOWEST_PRECEDENCE)
class DevelopmentFixtureInitializer implements ApplicationRunner {

    private final FixtureLoader fixtureLoader;

    DevelopmentFixtureInitializer(FixtureLoader fixtureLoader) {
        this.fixtureLoader = fixtureLoader;
    }

    @Override
    public void run(ApplicationArguments args) {
        fixtureLoader.seedDevelopmentFixtures();
    }
}
