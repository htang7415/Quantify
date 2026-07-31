#!/usr/bin/env bash
# Separate signed private catalog promotion/revocation; no public delivery path.
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_PRIVATE_CATALOG_STAGE:-}" != "1" ]]; then
  echo "Refusing private catalog staging; set QUANTIFY_AUTHORIZE_PRIVATE_CATALOG_STAGE=1." >&2
  exit 2
fi

repository_root="$(cd "$(dirname "$0")/../.." && pwd)"
export PYTHONPATH="$repository_root${PYTHONPATH:+:$PYTHONPATH}"
python_bin="${QUANTIFY_PYTHON_BIN:-$repository_root/.venv/bin/python}"
[[ -x "$python_bin" ]] || python_bin="python3"
exec "$python_bin" "$repository_root/deploy/aws/stage_private_release_catalog.py" "$@"
