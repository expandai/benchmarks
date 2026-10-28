"""Separate resumed runs when the overlay implementation or model transport changes.

Upstream hashes its resolved system, dataset and judge. The overlay adds behavior outside
that spec, so its own code and effective model endpoint must also participate in run identity.
This only affects new run directories; historical records are read without modification.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from harness import runner

from . import openrouter


def implementation_digest(directory: Path) -> str:
    """Hash package source and prompt/catalog files, without machine paths or credentials."""
    digest = hashlib.sha256()
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix in {".py", ".txt", ".toml"}:
            digest.update(path.name.encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
    return digest.hexdigest()


def execution_config() -> dict[str, Any]:
    transport = openrouter.transport_from_env()
    if transport == "openrouter":
        endpoint = os.environ.get(openrouter.BASE_URL_ENV) or openrouter.DEFAULT_BASE_URL
    else:
        endpoint = os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    return {
        "overlay_sha256": implementation_digest(Path(__file__).parent),
        "llm_transport": transport,
        "llm_base_url": endpoint.rstrip("/"),
    }


_installed = False


def install() -> None:
    """Extend upstream's run hash and config in process, leaving the pinned clone untouched."""
    global _installed
    if _installed:
        return
    upstream_hash = runner.config_hash
    upstream_init = runner.Runner.__init__

    def config_hash(spec, suite, judge_model) -> str:
        payload = {"upstream": upstream_hash(spec, suite, judge_model), **execution_config()}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:10]

    def initialize(self, *args, **kwargs) -> None:
        upstream_init(self, *args, **kwargs)
        self.config["execution"] = execution_config()

    runner.config_hash = config_hash
    runner.Runner.__init__ = initialize
    _installed = True
