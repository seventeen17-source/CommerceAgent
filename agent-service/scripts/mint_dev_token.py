"""Mint a local development JWT so a browser can authenticate against the Agent API.

Why a script instead of a Java endpoint
---------------------------------------
There is no login endpoint in this project by design (``research.md`` decision 8: no full
OAuth/OIDC). ``LocalJwtIssuer`` exists as a Spring bean, but wiring it to an HTTP endpoint would add
a production-shaped route whose only safe configuration is "registered in dev", and T014 already
showed how much care a test-only endpoint needs. A script has no route to leak: it runs on a
developer's machine, prints one token, and exits.

It is safe *because* the signing secret is already a shared, committed development placeholder
(``COMMERCE_JWT_SECRET`` default in ``application.yml``). This script therefore grants no access
that reading the repository does not already grant -- but it does print a credential, so:

* it refuses to run when ``ENVIRONMENT`` is not a development value, which stops it from being
  pointed at anything real;
* it prints the token to stdout only, never to a file.

Usage (from ``agent-service/``)::

    uv run python -m scripts.mint_dev_token customer-001

Then paste the printed token into the validation page at http://localhost:5173/.

Java analogy: this is the ``LocalJwtIssuer`` bean driven from a ``main`` method instead of from a
``@Profile("dev")`` controller. Same issuer, same claims, no new attack surface -- and one fewer
endpoint that has to be correct about which profile it is in.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta

import jwt

from app.config.settings import get_settings

#: The local fixture users seeded by ``DevelopmentFixtureInitializer`` (T014). Not enforced -- any
#: subject is signable -- but listing them here is what makes the script self-documenting, and it
#: gives a typo a chance to be noticed before it becomes a confusing 401.
KNOWN_DEV_USERS = ("customer-001", "customer-002", "approver-001")

#: Tokens are short-lived on purpose. A development token that lasts a week ends up pasted into a
#: note, a screenshot, or a test file, and this service's whole point is not storing credentials.
_DEFAULT_TTL_MINUTES = 60


def mint(user_id: str, *, ttl_minutes: int) -> str:
    """Build an HS256 token with exactly the claims this project's issuer produces.

    Claims kept minimal deliberately:

    * ``sub`` -- the user id. Java resolves the *current* role/status from ``commerce.users``, so a
      role claim here would be both unused and misleading.
    * ``iss``/``exp`` -- required by ``app.security.credentials.verify_credential``. A token without
      ``exp`` is rejected there, so emitting one would produce a token this service refuses.
    * no ``role``, no ``aud``. The first is Java's to decide; the second is not used by the issuer.
    """
    settings = get_settings()
    if settings.environment == "prod":
        raise SystemExit(
            "refusing to mint a development token with ENVIRONMENT=prod: "
            "this script signs with a committed placeholder secret"
        )

    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": settings.commerce_jwt_issuer,
            "sub": user_id,
            "iat": now,
            "exp": now + timedelta(minutes=ttl_minutes),
        },
        settings.commerce_jwt_secret,
        algorithm="HS256",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mint a local development JWT for the CommerceAgent Agent API."
    )
    parser.add_argument(
        "user_id",
        help=f"JWT subject, e.g. {' or '.join(KNOWN_DEV_USERS)}",
    )
    parser.add_argument(
        "--ttl-minutes",
        type=int,
        default=_DEFAULT_TTL_MINUTES,
        help=f"token lifetime in minutes (default {_DEFAULT_TTL_MINUTES})",
    )
    args = parser.parse_args(argv)

    if args.user_id in KNOWN_DEV_USERS:
        print(f"# fixture user {args.user_id}", file=sys.stderr)
    else:
        print(
            f"# note: {args.user_id!r} is not one of the T014 fixture users "
            f"({', '.join(KNOWN_DEV_USERS)}); Java will return 401 unless the user exists "
            "in commerce.users",
            file=sys.stderr,
        )

    # The token goes to stdout and nothing else does, so `... | clip` or a command substitution
    # captures exactly the credential.
    print(mint(args.user_id, ttl_minutes=args.ttl_minutes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
