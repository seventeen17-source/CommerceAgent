"""Every key a case expects must be a key the runner actually reads.

A typo in a case file is the quietest failure this suite can have: the YAML loads, the case runs,
nothing is asserted, and the case reports a pass -- the exact "assertion that cannot fail" shape the
US2 work kept running into. So the vocabulary is checked mechanically, and the keys are extracted
from the runner's own source *rather than listed here*: a hand-kept list would drift in precisely the
same way the case files do.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_EVAL_DIR = Path(__file__).resolve().parent.parent

#: ``expect.get("x")`` and ``expect["x"]`` are the two ways the runner reads an expectation.
_READ_KEYS = frozenset(
    re.findall(
        r"""expect(?:\.get\(|\[)\s*["']([A-Za-z][A-Za-z0-9]*)["']""",
        (_EVAL_DIR / "runner.py").read_text(encoding="utf-8"),
    )
)


def _cases() -> list[tuple[Path, dict[str, Any]]]:
    found: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted((_EVAL_DIR / "datasets").rglob("*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for case in payload.get("cases") or []:
            found.append((path, case))
    return found


def test_the_runner_vocabulary_could_be_read() -> None:
    """If this fails, the regex above stopped matching -- not the datasets."""
    assert "terminalStatus" in _READ_KEYS
    assert "writeToolForbidden" in _READ_KEYS


def test_every_expectation_key_is_one_the_runner_reads() -> None:
    unknown = [
        (path.name, case.get("caseId"), key)
        for path, case in _cases()
        for key in (case.get("expect") or {})
        if key not in _READ_KEYS
    ]

    assert unknown == [], f"cases expect keys the runner never reads: {unknown}"


def test_every_case_asserts_something() -> None:
    """A case with an empty ``expect`` block cannot fail, so it is not a case."""
    empty = [
        (path.name, case.get("caseId"))
        for path, case in _cases()
        if not (case.get("expect") or {})
    ]

    assert empty == [], f"cases with nothing asserted: {empty}"
