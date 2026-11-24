#!/usr/bin/env bash
# Start the API. Without --scenario, each service uses its default simulated incident.
# Usage: scripts/serve.sh [--scenario <id>] [uvicorn args...]   (PORT defaults to 8000)
set -euo pipefail
cd "$(dirname "$0")/.."

args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --scenario|-s) [[ $# -ge 2 ]] || { echo "--scenario needs a value" >&2; exit 2; }
                   scenario="$2"; shift 2 ;;
    --scenario=*)  scenario="${1#*=}"; shift ;;
    *)             args+=("$1"); shift ;;
  esac
done

if [[ -n "${scenario:-}" ]]; then
  .venv/bin/python -c "
import sys
from simulator import scenarios
ids = scenarios.scenario_ids()
sys.exit(0 if sys.argv[1] in ids else f'unknown scenario: {sys.argv[1]} (choose from: {\", \".join(ids)})')" "$scenario"
  export ONCALL_SCENARIO="$scenario"
fi
exec .venv/bin/python -m uvicorn app.api.main:app --port "${PORT:-8000}" ${args[@]+"${args[@]}"}
