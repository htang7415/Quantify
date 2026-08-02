#!/usr/bin/env bash
set -euo pipefail

if [[ "${QUANTIFY_AUTHORIZE_AWS_PUBLIC_AGENT_WAF_CHECK:-}" != "1" ]]; then
  echo "Set QUANTIFY_AUTHORIZE_AWS_PUBLIC_AGENT_WAF_CHECK=1 to run the read-only public-agent WAF check." >&2
  exit 2
fi

exec python3 "$(dirname "$0")/check_public_agent_waf.py" "$@"
