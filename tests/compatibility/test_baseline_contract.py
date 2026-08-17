"""Executable checks for the Step 0 baseline contract.

These tests intentionally assert the current baseline, not the future Step 1 API.
They keep the inventory honest while the reference service is exercised separately.
"""

from pathlib import Path

from sinan.models.enums import PageStatus, SessionStatus


ROOT = Path(__file__).parents[2]


def test_step_zero_matrix_documents_exist():
    matrix_dir = ROOT / "docs" / "compatibility"
    expected = {
        "api-matrix.md",
        "request-response-matrix.md",
        "state-matrix.md",
        "event-matrix.md",
        "storage-matrix.md",
        "runtime-matrix.md",
        "behavior-cases.md",
    }
    assert {path.name for path in matrix_dir.iterdir()} == expected


def test_current_state_enums_are_documented_baseline():
    state_doc = (ROOT / "docs/compatibility/state-matrix.md").read_text()
    assert all(status.value in state_doc for status in SessionStatus)
    assert all(status.value in state_doc for status in PageStatus)


def test_behavior_inventory_contains_all_required_cases():
    cases = (ROOT / "docs/compatibility/behavior-cases.md").read_text()
    for case_id in range(1, 29):
        assert f"| {case_id} |" in cases
