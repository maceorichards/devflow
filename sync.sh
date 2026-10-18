#!/usr/bin/env bash
# devflow: rebuild and install managed skills. See README.md.
set -euo pipefail
exec python3 -I "$(cd "$(dirname "$0")" && pwd)/lib/sync.py" "$@"
