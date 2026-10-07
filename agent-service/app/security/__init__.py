"""Inbound security for the Agent API (T018).

``credentials`` answers "is this a token this project issued, and is it still valid?" and returns a
value that deliberately cannot answer "who". ``dependencies`` chains that local check into the
authoritative ``GET /me`` lookup, which is the only source of identity.
"""
