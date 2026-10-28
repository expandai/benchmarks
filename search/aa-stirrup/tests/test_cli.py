"""Offline resume and failure-status checks for the AA command line."""

from pathlib import Path
from unittest.mock import AsyncMock
import json

import pytest

from aastirrup import __main__ as cli
from aastirrup import runner
from .test_agent import Q


def test_prepare_resume_preserves_manifest_and_rejects_different_settings(tmp_path: Path) -> None:
    arguments = ["prepare", "--run", str(tmp_path), "--n", "20"]
    assert cli.main(arguments) == 0
    original = (tmp_path / "manifest.json").read_bytes()
    assert cli.main(arguments) == 2
    assert cli.main(arguments + ["--resume"]) == 0
    assert (tmp_path / "manifest.json").read_bytes() == original
    assert cli.main(arguments + ["--resume", "--seed", "99"]) == 2
    with pytest.raises(ValueError, match="settings differ"):
        cli.main(arguments + ["--resume", "--transport", "chat"])


def test_run_reports_task_failures_to_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert cli.main(["prepare", "--run", str(tmp_path), "--n", "20"]) == 0
    run_system = AsyncMock(return_value=1)
    monkeypatch.setattr(runner, "run_system", run_system)
    assert cli.main(["run", "--run", str(tmp_path), "--systems", "expand"]) == 1
    run_system.return_value = 0
    assert cli.main(["run", "--run", str(tmp_path), "--systems", "expand"]) == 0


def test_run_rejects_model_change_before_provider_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert cli.main(["prepare", "--run", str(tmp_path), "--n", "20"]) == 0
    monkeypatch.setattr(cli.llm, "ANSWER_MODEL", "different-model")
    with pytest.raises(ValueError, match="settings differ"):
        cli.main(["run", "--run", str(tmp_path), "--systems", "expand"])


async def test_run_system_counts_failures_and_skips_complete_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk = AsyncMock()
    monkeypatch.setattr(runner.llm, "openrouter_client", lambda: sdk)
    monkeypatch.setattr(runner.llm, "model_only_answer", AsyncMock(side_effect=RuntimeError("offline failure")))
    assert await runner.run_system("model-only", [Q], tmp_path, "responses", 1) == 1
    sdk.close.assert_awaited_once()
    path = runner.task_path(tmp_path, "model-only", Q)
    path.write_text(json.dumps({"status": "complete"}))
    assert await runner.run_system("model-only", [Q], tmp_path, "responses", 1) == 0
    sdk.close.assert_awaited_once()


def test_aa_resume_rejects_changed_endpoint_and_legacy_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner.check_run_config("expand", tmp_path, "responses")
    runner.check_run_config("expand", tmp_path, "responses")
    monkeypatch.setenv("EXPAND_SEARCH_BASE_URL", "https://search.example")
    with pytest.raises(ValueError, match="settings changed"):
        runner.check_run_config("expand", tmp_path, "responses")
    legacy = tmp_path / "legacy" / "model-only"
    legacy.mkdir(parents=True)
    (legacy / "aao-001.json").write_text('{"status": "complete"}')
    with pytest.raises(ValueError, match="historical records"):
        runner.check_run_config("model-only", legacy.parent, "responses")
