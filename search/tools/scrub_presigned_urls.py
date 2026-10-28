"""Replace the query string of presigned / signed URLs in the stored records with a fixed marker.

Search providers occasionally return presigned S3 links (``?X-Amz-Credential=AKIA…&X-Amz-Signature=…``
or ``?AWSAccessKeyId=AKIA…&Signature=…&Expires=…``) and Azure SAS links (``?sv=…&se=…&sig=…``,
``?jwt=…``). The key ids and signatures are the third party's, but secret scanners flag them
regardless of context, so every such URL in ``runs/`` and ``aa-stirrup/runs/`` has its query string
replaced by ``?<presigned-params-redacted>``; the path stays. Run after
``tools/strip_result_details.py``, which already drops citation and fetch URLs; what remains is in
model answers, errors and logs.

    python3 -I tools/scrub_presigned_urls.py            # rewrite in place, print the count
    python3 -I tools/scrub_presigned_urls.py --check    # exit 1 if anything would change
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD_DIRS = ("runs", "aa-stirrup/runs")
PRESIGNED_PARAMS = ("X-Amz-Credential", "X-Amz-Signature", "X-Amz-Security-Token", "AWSAccessKeyId", "Signature=", "AKIA", "sig=", "jwt=", "sv=", "se=")
MARKER = "?<presigned-params-redacted>"
# A URL whose query string carries any presigned or SAS parameter (Azure: ``sig``/``jwt``, or the
# ``sv``/``se`` dates); stops at JSON/XML/whitespace delimiters.
_SAS = r"(?:(?<=[?&])(?:sig|jwt)=|(?<=[?&])(?:sv|se)=20\d\d-)"
_URL = re.compile(r'(https?://[^\s"<>\\?]+)\?([^\s"<>\\]*(?:X-Amz-Credential|X-Amz-Signature|X-Amz-Security-Token|AWSAccessKeyId|Signature=|AKIA[0-9A-Z]{16}|' + _SAS + r')[^\s"<>\\]*)')


def scrub(text: str) -> tuple[str, int]:
    return _URL.subn(lambda m: m.group(1) + MARKER, text)


def main() -> int:
    check = "--check" in sys.argv
    urls = files = 0
    for rel in RECORD_DIRS:
        for path in (ROOT / rel).rglob("*"):
            if not path.is_file() or path.suffix not in {".json", ".jsonl", ".md", ".log", ".txt"}:
                continue
            raw = path.read_text(encoding="utf-8", errors="surrogateescape")
            if not any(p in raw for p in PRESIGNED_PARAMS):
                continue
            new, n = scrub(raw)
            if n:
                if not check:
                    path.write_text(new, encoding="utf-8", errors="surrogateescape")
                urls += n; files += 1
                print(f"{n:3d} {path.relative_to(ROOT)}")
    print(f"{urls} presigned URL(s) {'would be scrubbed' if check else 'scrubbed'} in {files} file(s)")
    return 1 if (check and urls) else 0


if __name__ == "__main__":
    sys.exit(main())
