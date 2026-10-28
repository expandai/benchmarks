"""Completed records must not silently turn into smaller or misaligned paired cohorts."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runs"))
from paired import aa_scores, harness_scores, paired  # noqa: E402


def write_grade(root, task_id, grade):
    task = root / "tasks" / task_id
    task.mkdir(parents=True)
    (task / "grade.json").write_text(json.dumps(grade))


def test_pairing_rejects_equal_size_but_different_task_sets():
    with pytest.raises(ValueError, match="same non-empty set"):
        paired({"a": 1.0, "b": 0.0}, {"a": 1.0, "c": 1.0})


def test_terminal_failure_stays_in_paired_denominator(tmp_path):
    write_grade(tmp_path, "a", {"task_id": "a", "scores": {"score": 1.0}})
    failed = tmp_path / "tasks" / "b"
    failed.mkdir()
    (failed / "error.json").write_text("{}")
    assert harness_scores(tmp_path, "score", 2) == {"a": 1.0, "b": 0.0}
    assert harness_scores(tmp_path, "score", 3) is None


@pytest.mark.parametrize("grade", [
    {"task_id": "wrong", "scores": {"score": 1.0}},
    {"task_id": "a", "scores": {}},
    {"task_id": "a", "scores": {"score": float("nan")}},
])
def test_invalid_completed_grade_fails_closed(tmp_path, grade):
    write_grade(tmp_path, "a", grade)
    with pytest.raises((ValueError, KeyError)):
        harness_scores(tmp_path, "score", 1)


def test_corrupt_completed_grade_is_not_silently_dropped(tmp_path):
    write_grade(tmp_path, "a", {})
    (tmp_path / "tasks" / "a" / "grade.json").write_text("{")
    with pytest.raises(json.JSONDecodeError):
        harness_scores(tmp_path, "score", 1)


@pytest.mark.parametrize("record", [
    {"id": "aao-999", "status": "complete", "grade": "CORRECT"},
    {"id": "aao-001", "status": "complete", "grade": "invalid"},
])
def test_aa_completed_record_requires_matching_id_and_valid_grade(tmp_path, record):
    (tmp_path / "aao-001.json").write_text(json.dumps(record))
    with pytest.raises(ValueError):
        aa_scores(tmp_path, 1)
