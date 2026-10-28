"""Shared offline helpers. No test opens a network connection or reads a real key."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

sys.dont_write_bytecode = True  # keep the pinned upstream tree byte-identical

# Set before huggingface_hub is first imported: cached dataset reads only, no telemetry.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

FIXTURES = Path(__file__).with_name("fixtures")
PROVIDER_ENV = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "EXA_API_KEY",
    "BRAVE_SEARCH_API_KEY",
    "BRAVE_API_KEY",
    "PARALLEL_API_KEY",
    "PARALLELS_API_KEY",
    "PERPLEXITY_API_KEY",
    "TAVILY_API_KEY",
    "EXPAND_API_KEY",
    "EXPAND_SEARCH_BASE_URL",
    "FIRECRAWL_API_KEY",
    "OPENROUTER_API_KEY",
    "OPEN_ROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "BAKEOFF_LLM_TRANSPORT",
    "DEEPSEEK_API_KEY",
)


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Start every test with no provider credentials and no retry delays."""
    for name in PROVIDER_ENV:
        monkeypatch.delenv(name, raising=False)
    real_sleep = asyncio.sleep

    async def no_sleep(_seconds):
        await real_sleep(0)

    import bakeoff._http
    import bakeoff.openrouter

    monkeypatch.setattr(bakeoff._http.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(bakeoff.openrouter.asyncio, "sleep", no_sleep)
    # Each test starts on upstream's direct OpenAI route unless it installs OpenRouter.
    bakeoff.openrouter.uninstall()
    yield
    bakeoff.openrouter.uninstall()
