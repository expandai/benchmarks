"""Shell orchestration must propagate failures from background benchmark processes."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("script", ["run-suite.sh", "pilot-20/run-pilot.sh"])
@pytest.mark.parametrize("failing_system, expected_status", [("bad", 1), ("none", 0)])
def test_run_suite_propagates_child_status(tmp_path, failing_system, expected_status, script):
    runs = tmp_path / "runs"
    runs.mkdir()
    for name in (script, "env.sh"):
        (runs / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "runs" / name, runs / name)
    bench = tmp_path / "bench"
    bench.write_text('#!/bin/sh\ncase " $* " in *" --system bad "*) exit 2;; esac\nexit 0\n')
    bench.chmod(0o755)
    environment = {
        **os.environ,
        "OPENROUTER_API_KEY": "offline-test",
        "BAKEOFF_ENV_FILE": str(tmp_path / "absent.env"),
        "PASSES": "1",
    }
    suite = ["fake-suite"] if script == "run-suite.sh" else []
    result = subprocess.run(
        ["sh", str(runs / script), *suite, failing_system, "good"],
        env=environment, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == expected_status, result.stderr
    assert "good limit=" in result.stdout
