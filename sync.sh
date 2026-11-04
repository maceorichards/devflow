#!/usr/bin/env bash
# devflow: rebuild and install managed skills. See README.md.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"

# Interpreter probe: the first candidate that runs and is Python 3.9+ wins. A missing command,
# the Windows Store shim (exits non-zero) or an older Python fails the check and is skipped.
check='import sys; sys.exit(0 if tuple(sys.version_info[:2]) >= (3, 9) else 1)'
for candidate in python3 python "py -3"; do
  # $candidate is unquoted on purpose: "py -3" is a command plus its argument.
  if $candidate -I -c "$check" >/dev/null 2>&1; then
    exec $candidate -I -X utf8 "$here/lib/sync.py" "$@"
  fi
done

echo "devflow needs Python 3.9+; tried: python3, python, py -3" >&2
exit 1
