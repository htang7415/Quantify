#!/usr/bin/env bash
set -euo pipefail
[[ "${QUANTIFY_AUTHORIZE_AWS_PUBLIC_AGENT_BURST_CHECK:-}" == "1" ]] || { echo "Set QUANTIFY_AUTHORIZE_AWS_PUBLIC_AGENT_BURST_CHECK=1." >&2; exit 2; }
exec python3 "$(dirname "$0")/check_public_agent_burst.py" "$@"
