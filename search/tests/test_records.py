"""Report inputs must identify a single run, independent of directory ordering."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runs"))
from _records import result_search_usd, run_dirs  # noqa: E402
from bakeoff.expand import EXPAND_SEARCH_COST_PER_REQUEST  # noqa: E402


def write_config(path, suite="suite", system="rag-example"):
    path.mkdir(parents=True)
    (path / "config.json").write_text(json.dumps({"suite": suite, "system": {"name": system}}))


@pytest.mark.parametrize("separate_roots", [False, True])
def test_duplicate_runs_fail_with_both_paths_and_selection_guidance(tmp_path, separate_roots):
    first_root = tmp_path / "original"
    second_root = tmp_path / "rerun" if separate_roots else first_root
    first = first_root / "example-aaa"
    second = second_root / "example-bbb"
    write_config(first)
    write_config(second)
    roots = [first_root, second_root] if separate_roots else [first_root]
    with pytest.raises(ValueError) as error:
        run_dirs(roots, "suite")
    message = str(error.value)
    assert str(first) in message and str(second) in message
    assert "suite" in message and "rag-example" in message
    assert "Select exactly one run" in message


def test_other_suites_do_not_make_the_requested_suite_ambiguous(tmp_path):
    selected = tmp_path / "selected"
    write_config(selected)
    write_config(tmp_path / "other-suite", suite="other")
    assert run_dirs([tmp_path], "suite") == {"rag-example": (selected, tmp_path)}


def test_expand_search_cost_is_billed_searches_at_list_price():
    billed = {"task_id": "t", "search_queries": ["q"], "search_cost_usd": 0.004}
    refunded = {"task_id": "t", "search_queries": ["q"], "search_cost_usd": 0.0}
    assert result_search_usd("expand", billed) == EXPAND_SEARCH_COST_PER_REQUEST
    assert result_search_usd("expand", refunded) == 0.0
    # Other searchers keep the stored cost.
    assert result_search_usd("exa-fast-highlights", billed) == 0.004
    assert result_search_usd(None, refunded) == 0.0
    with pytest.raises(ValueError, match="more than one search"):
        result_search_usd("expand", {**billed, "search_queries": ["a", "b"]})
