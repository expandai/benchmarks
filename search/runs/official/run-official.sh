#!/bin/sh
# The official-grader suites now run through ../run-suite.sh (same arguments, same output); kept for old commands.
exec "$(cd "$(dirname "$0")/.." && pwd)/run-suite.sh" "$@"
