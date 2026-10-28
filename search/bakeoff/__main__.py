"""``python -m bakeoff``: the upstream ``bench`` CLI with the bakeoff's searchers and suites registered.

Same subcommands and flags as ``uv run bench`` at the pinned commit.
"""

from __future__ import annotations

import argparse
import sys

from harness import cli

from . import openrouter
from .register import PROVIDER_KEYS, added_systems, install


def main(argv: list[str] | None = None) -> None:
    install()
    parser = cli.build_parser()
    parser.prog = "python -m bakeoff"
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    keys = ", ".join(" or ".join(names) for names in PROVIDER_KEYS.values())
    parser.epilog = (
        "Bakeoff systems added to the upstream catalog:\n  "
        + "\n  ".join(added_systems())
        + f"\nCredentials: {keys}; EXPAND_SEARCH_BASE_URL (default https://api.expand.ai)."
        + f"\n{openrouter.TRANSPORT_ENV}=openrouter sends openai/* answer and judge calls "
        + f"through OpenRouter ({' or '.join(openrouter.KEY_ENV)}) instead of OpenAI."
    )
    args = parser.parse_args(argv)
    try:
        status = args.func(args)
    except (ValueError, KeyError, FileNotFoundError) as error:
        cli.console.print(f"[red]{error}[/red]")
        status = 2
    if openrouter.is_installed() and openrouter.STATS.calls:
        cli.console.print(openrouter.STATS.summary())
    sys.exit(status)


if __name__ == "__main__":
    main()
