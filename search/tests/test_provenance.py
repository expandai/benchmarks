"""Different search endpoints and model transports never share resumable run directories."""

from harness.llm.judge import Judge
from harness.runner import Runner
from harness.systems import Catalog
from benchmarks import get_suite

from bakeoff import register


def make_runner():
    register.install()
    return Runner(Catalog.load().resolve("rag-expand"), get_suite("webcode-rag"), judge=Judge("openai/gpt-6-luna"))


def test_expand_endpoint_participates_in_spec_and_hash(monkeypatch):
    default = make_runner()
    assert default.config["system"]["searcher"]["base_url"] == "https://api.expand.ai"
    monkeypatch.setenv("EXPAND_SEARCH_BASE_URL", "https://search.example/")
    custom = make_runner()
    assert custom.config["system"]["searcher"]["base_url"] == "https://search.example"
    assert custom.run_dir != default.run_dir
    assert make_runner().run_dir == custom.run_dir


def test_model_transport_and_endpoint_participate_in_hash(monkeypatch):
    direct = make_runner()
    monkeypatch.setenv("BAKEOFF_LLM_TRANSPORT", "openrouter")
    router = make_runner()
    assert direct.run_dir != router.run_dir
    assert router.config["execution"]["llm_transport"] == "openrouter"
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://proxy.example/api/v1")
    assert make_runner().run_dir != router.run_dir
