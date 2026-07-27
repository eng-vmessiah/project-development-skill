"""Spec-local index test; canonical implementation tests live in tests/fleet."""
from pathlib import Path


def test_canonical_supervision_tests_are_registered() -> None:
    root = Path(__file__).parents[3]
    assert (root / "tests/fleet/test_supervision.py").is_file()
    assert (root / "tests/fleet/test_handoff.py").is_file()
