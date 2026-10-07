package com.seventeen17.commerceagent;

import org.springframework.boot.SpringApplication;

public class TestCommerceBackendApplication {

    public static void main(String[] args) {
        SpringApplication.from(CommerceBackendApplication::main)
                .with(TestcontainersConfiguration.class)
                .run(args);
    }
}
