"""The composite index's arithmetic and bootstrap on synthetic per-task scores (offline)."""

import importlib.util
import sys
from pathlib import Path

import numpy as np

RUNS = Path(__file__).resolve().parents[1] / "runs"


def load_index():
    sys.path.insert(0, str(RUNS))
    spec = importlib.util.spec_from_file_location("runs_index", RUNS / "index.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_index_is_the_equal_weight_mean_of_dataset_accuracies():
    index = load_index()
    aligned = {
        index.EXPAND: [np.array([1.0, 1.0, 0.0, 0.0]), np.array([1.0, 1.0])],  # 50 % and 100 %
        "rag-other": [np.array([1.0, 0.0, 0.0, 0.0]), np.array([1.0, 0.0])],  # 25 % and 50 %
    }
    result = index.bootstrap(aligned)
    assert result[index.EXPAND]["index"] == 75.0  # (50 + 100) / 2, regardless of dataset size
    assert result["rag-other"]["index"] == 37.5
    assert result["rag-other"]["per_dataset"] == [25.0, 50.0]
    assert result[index.EXPAND]["expand_minus"] is None
    assert result["rag-other"]["expand_minus"]["diff"] == 37.5


def test_identical_systems_have_a_zero_paired_difference():
    index = load_index()
    rng = np.random.default_rng(1)
    vectors = [rng.integers(0, 2, size=200).astype(float), rng.integers(0, 2, size=50).astype(float)]
    result = index.bootstrap({index.EXPAND: vectors, "rag-copy": [v.copy() for v in vectors]})
    paired = result["rag-copy"]["expand_minus"]
    assert paired["diff"] == 0.0 and paired["low"] == 0.0 and paired["high"] == 0.0
    assert result["rag-copy"]["low"] <= result["rag-copy"]["index"] <= result["rag-copy"]["high"]


def test_markdown_rounds_raw_accuracy_once():
    index = load_index()
    # Actual WebCode counts: two-stage rounding reverses the correct last digit in both rows.
    vectors = {
        index.EXPAND: [np.array([1.0] * 270 + [0.0] * 37)],
        "rag-other": [np.array([1.0] * 239 + [0.0] * 68)],
    }
    result = index.bootstrap(vectors)
    assert result[index.EXPAND]["per_dataset"] == [270 / 307 * 100]
    table = index.markdown(["WebCode"], result)
    assert "| 87.9 |" in table
    assert "| 77.9 |" in table
