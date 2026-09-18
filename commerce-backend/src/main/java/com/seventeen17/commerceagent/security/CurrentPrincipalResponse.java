package com.seventeen17.commerceagent.security;

import com.seventeen17.commerceagent.user.UserRole;

/** Authoritative authenticated principal exposed to trusted API consumers such as the Agent Service. */
public record CurrentPrincipalResponse(String userId, UserRole role) {}
