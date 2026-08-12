#!/usr/bin/env bash
# User-run launcher: capture the 3-page bundle for a season's not-yet-captured
# contests. SAFE RATE: 1-2 WORKERS MAX -- run this script as 1-2 separate
# PROCESSES with disjoint --shard i/N, never 4+. See README.md.
#   ./scripts/run_02_games.sh --season 2026                  # 1 worker
#   ./scripts/run_02_games.sh --season 2026 --shard 0/2 &     # worker 0 of 2
#   ./scripts/run_02_games.sh --season 2026 --shard 1/2 &     # worker 1 of 2
# Canary-vendor transport (creds live in canary_vendors.toml, not .Renviron):
#   NCAA_VENDOR=decodo_patchright ./scripts/run_02_games.sh --season 2026
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1   # -> ncaa-mbb-hoops-raw repo root
ROOT="$(pwd)"
SDV_PY="${SDV_PY:-C:/Users/saiem/Documents/GitHub-Data/sdv-dev/sdv-py}"

# ProxyBonanza creds are only the FALLBACK transport. With NCAA_VENDOR set
# (decodo_patchright), capture rides canary_vendors.toml and never touches PB --
# demanding PB creds there hard-exits a perfectly valid Decodo run. Same guard
# run_01_schedules.sh already uses.
#
# Keyed on the ENV VAR, not the --vendor CLI flag: run_mbb_backfill.sh drives
# this script and exports NCAA_VENDOR, it does not pass --vendor. The old
# flag-keyed form was recorded as a latent bug in docs/SCRAPING_NOTES.md
# (2026-08-02) precisely because a vendor-driven campaign still hit the PB
# check and exited 2.
if [ -z "${NCAA_VENDOR:-}" ]; then
  RENV="${HOME}/.Renviron"
  [ -f "$RENV" ] || RENV="${HOME}/Documents/.Renviron"
  getcred() { grep -E "^$1=" "$RENV" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d '\r'; }

  export SDV_PY_PROXYBONANZA_KEY="$(getcred PROXYBONANZA_API_KEY)"
  export SDV_PY_PROXYBONANZA_PKG="$(getcred PROXY_PKG)"
  if [ -z "${SDV_PY_PROXYBONANZA_KEY}" ] || [ -z "${SDV_PY_PROXYBONANZA_PKG}" ]; then
    echo "ERROR: no NCAA_VENDOR set and no proxy creds in ${RENV}" >&2
    exit 2
  fi
  echo "proxy creds loaded from ${RENV} (values hidden)"
else
  echo "transport: NCAA_VENDOR=${NCAA_VENDOR} (canary_vendors.toml; ProxyBonanza not used)"
fi

# .venv layout is OS-dependent: Linux/droplet = .venv/bin, Windows = .venv/Scripts
if [ -x "${SDV_PY}/.venv/bin/python" ]; then PY="${PY:-${SDV_PY}/.venv/bin/python}"
else PY="${PY:-${SDV_PY}/.venv/Scripts/python.exe}"; fi

export PYTHONPATH="${SDV_PY}:${ROOT}/python"
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

mkdir -p logs
LOG="logs/capture_$(date +%Y%m%d_%H%M%S).log"
echo "log -> ${LOG}  (watch: tail -f ${LOG})"
"$PY" python/ncaa_mbb_02_games_scrape.py "$@" 2>&1 | tee -a "${LOG}"
rc=${PIPESTATUS[0]}
echo "EXIT=${rc}" | tee -a "${LOG}"
# Propagate the python exit code -- a bare trailing `echo` would mask a
# ban hard-stop as success (it did: the 2026-07-13 backfill reported rc=0).
exit "${rc}"
