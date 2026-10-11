#!/usr/bin/env bash
# Wrapper: loads secrets.env, then runs the Prolific CLI.
# Usage: scripts/prolific.sh whoami
#        scripts/prolific.sh study create -t prolific/generated/pilot_anxiety.json
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ ! -f "$ROOT/secrets.env" ]]; then
  echo "Missing secrets.env (copy secrets.env.example and add PROLIFIC_TOKEN)" >&2; exit 1
fi
set -a; source "$ROOT/secrets.env"; set +a
[[ -n "${PROLIFIC_TOKEN:-}" ]] || { echo "PROLIFIC_TOKEN is empty in secrets.env" >&2; exit 1; }
BIN="$(command -v prolific || echo "$ROOT/bin/prolific.exe")"
exec "$BIN" "$@"
