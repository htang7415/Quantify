#!/usr/bin/env bash
# Read-only private catalog verification; it never changes a stage or delivery path.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_PRIVATE_CATALOG_CHECK:-}" != "1" ]]; then
  echo "Refusing private catalog check; set QUANTIFY_AUTHORIZE_PRIVATE_CATALOG_CHECK=1." >&2
  exit 2
fi

repository_root="$(cd "$(dirname "$0")/../.." && pwd)"
export PYTHONPATH="$repository_root${PYTHONPATH:+:$PYTHONPATH}"
python_bin="${QUANTIFY_PYTHON_BIN:-$repository_root/.venv/bin/python}"
[[ -x "$python_bin" ]] || python_bin="python3"
exec "$python_bin" "$repository_root/deploy/aws/check_private_release_catalog.py" "$@"
