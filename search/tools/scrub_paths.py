"""Replace the machine paths a run wrote into stored records and logs with ``<repo>`` / ``<home>`` / ``<venv>``.

``bench`` and ``aa`` embed absolute paths in tracebacks and log lines. A path into a checkout of this
directory (anything up to the first ``bakeoff/``, ``upstream/``, ``runs/``, ``aa-stirrup/``, ``.venv/``,
... component) becomes ``<repo>``; any other path under the home directory of a user who produced
such a repo path becomes ``<home>``; a virtualenv outside the checkout (under ``/tmp``, ``/private/tmp``
or ``/var/folders``, in front of ``lib/python3.x`` or ``bin/python``) becomes ``<venv>``. A path the log
renderer wrapped onto the next line is rejoined first. Paths of other users (for example inside a web
page title a provider returned) and ``/Users/...`` inside a URL are left alone.

    python3 -I tools/scrub_paths.py            # rewrite in place, print the count
    python3 -I tools/scrub_paths.py --check    # exit 1 if anything would change (CI)

Only text files under runs/ and aa-stirrup/runs/ are read; JSON stays valid because the replacement
is a plain substring with no quotes or backslashes.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOTS = [ROOT / "runs", ROOT / "aa-stirrup" / "runs"]
SUFFIXES = {".json", ".jsonl", ".log", ".txt", ".md"}
# Top-level entries of this directory; the shortest prefix in front of one of them is the checkout root.
REPO_ENTRIES = ("bakeoff", "upstream", "runs", "aa-stirrup", "tests", "tools", r"\.venv", r"\.hf-cache", r"\.tiktoken-cache")
# The lookbehind keeps `/Users/...` inside a URL (preceded by a host or path character) untouched.
_NOT_IN_URL = r"(?<![A-Za-z0-9.])"
_ENTRY = r"(?=/(?:" + "|".join(REPO_ENTRIES) + r")\b)"
REPO_PATH = re.compile(_NOT_IN_URL + r"/Users/(?P<user>[A-Za-z0-9_.-]+)(?:/[A-Za-z0-9_.-]+)*?" + _ENTRY)
VENV_PATH = re.compile(
    _NOT_IN_URL + r"/(?:private/)?(?:tmp|var/folders)/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*?(?=/(?:lib/python\d|bin/python))"
)
# Rich wraps a long path at the console width: a line ending in a /Users/ path, then a line that is
# only the rest of it. Rejoined when the halves only form a repo path together.
WRAPPED = re.compile(r"(?m)(" + _NOT_IN_URL + r"/Users/[A-Za-z0-9_./-]*)\n([A-Za-z0-9_.-]+/[A-Za-z0-9_./-]*)$")
# The same wrap after an earlier scrub: ``<repo>`` alone on a line, then ``<checkout-dir>/runs/...``.
WRAPPED_SCRUBBED = re.compile(r"(?m)^<repo>\n[A-Za-z0-9_.-]+" + _ENTRY)
MARKERS = ("/Users/", "/tmp/", "/var/folders/", "<repo>\n")


def home_pattern(users: set[str]) -> re.Pattern[str] | None:
    if not users:
        return None
    names = "|".join(re.escape(user) for user in sorted(users))
    return re.compile(_NOT_IN_URL + r"/Users/(?:" + names + r")(?=/|\b)")


def unwrap(text: str) -> str:
    def join(match: re.Match[str]) -> str:
        head, tail = match.group(1), match.group(2)
        if REPO_PATH.search(head) is None and REPO_PATH.match(head + tail):
            return head + tail
        return match.group(0)

    return WRAPPED_SCRUBBED.sub("<repo>", WRAPPED.sub(join, text))


def scrub(text: str, users: set[str]) -> str:
    text = REPO_PATH.sub("<repo>", unwrap(text))
    text = VENV_PATH.sub("<venv>", text)
    home = home_pattern(users)
    return home.sub("<home>", text) if home else text


def candidates() -> list[tuple[Path, str]]:
    """Every text record under ROOTS that may hold a machine path (MARKERS)."""
    found = []
    for root in ROOTS:
        if not root.exists():
            continue
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                path = Path(dirpath) / name
                if path.suffix not in SUFFIXES:
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                if any(marker in text for marker in MARKERS):
                    found.append((path, text))
    return found


def main() -> int:
    check = "--check" in sys.argv
    files = candidates()
    users = {match.group("user") for _path, text in files for match in REPO_PATH.finditer(unwrap(text))}
    changed = 0
    for path, original in files:
        updated = scrub(original, users)
        if updated != original:
            changed += 1
            if not check:
                path.write_text(updated, encoding="utf-8")
    print(f"{'would change' if check else 'scrubbed'} {changed} file(s)")
    return 1 if (check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())
