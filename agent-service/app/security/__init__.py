"""Security primitives shared by the Agent runtime (T017/T018).

``secrets`` owns the persistence-boundary guard: the single rule that decides whether a structure
may be written to durable storage. It lives here rather than in ``app/agent`` or ``app/trace``
because both of those need it, and a rule with two copies is two rules.
"""
