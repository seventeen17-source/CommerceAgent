package com.seventeen17.commerceagent.fixture;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * T063-live: registers the fault interceptor on exactly one path.
 *
 * <p>The narrow pattern is the point. A globally registered interceptor would mean every future
 * endpoint is one boolean away from failing under eval, and the next person adding a route would have
 * to know about this class to notice. Binding it to the logistics read keeps the blast radius equal
 * to the scenario being evaluated.
 */
@Configuration
@Profile({"test", "eval"})
class EvalFaultWebConfig implements WebMvcConfigurer {

    private final EvalFaultInterceptor interceptor;

    EvalFaultWebConfig(EvalFaultInterceptor interceptor) {
        this.interceptor = interceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(interceptor).addPathPatterns("/api/v1/orders/*/logistics");
    }
}
