package com.seventeen17.commerceagent.fixture;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.Profile;

class FixtureProfileDeclarationTest {

    @Test
    void resetEndpointIsRegisteredOnlyForTestAndEval() {
        Profile profile = EvalFixtureController.class.getAnnotation(Profile.class);
        assertArrayEquals(new String[] {"test", "eval"}, profile.value());
    }

    @Test
    void developmentInitializerIsRegisteredOnlyForDev() {
        Profile profile = DevelopmentFixtureInitializer.class.getAnnotation(Profile.class);
        assertArrayEquals(new String[] {"dev"}, profile.value());
    }
}
