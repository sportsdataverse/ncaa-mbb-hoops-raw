#!/usr/bin/env bash
# Droplet (Linux) launcher for the NCAA MBB PBP capture, riding the Decodo
# US-residential sticky port pool in canary_vendors.toml.
#
# Twin of ncaa-wbb-hoops-raw/scripts/droplet_wbb_capture.sh. The base runners
# default to the Windows dev-box venv; this only exports the droplet's SDV_PY +
# the vendor transport and delegates. All other knobs stay env-only, exactly as
# run_02_games.sh documents them.
#
# Usage:
#   ./scripts/droplet_mbb_capture.sh --season 2026 --max-contests 25
#   ./scripts/droplet_mbb_capture.sh --season 2026 --shard 0/2 &
#
# Survive an SSH disconnect:
#   tmux new -s mbb './scripts/droplet_mbb_capture.sh --season 2026'
#   # or: nohup ./scripts/droplet_mbb_capture.sh --season 2026 &
#
# Watch live:  tail -f logs/capture_<ts>.log   (path printed on start)
#
# NOT a cron entry point. Capture is user-run at a hand-held pace: stats.ncaa.org
# bans per-IP and permanently, so an unattended loop is how a pool gets burned.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

export SDV_PY="${SDV_PY:-/mnt/sdv_repos/sdv-py}"
export NCAA_VENDOR="${NCAA_VENDOR:-decodo_patchright}"
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

if [ ! -f canary_vendors.toml ]; then
  echo "ERROR: canary_vendors.toml missing (holds the Decodo ports; gitignored)." >&2
  echo "       The WBB twin has one at ../ncaa-wbb-hoops-raw/canary_vendors.toml." >&2
  exit 2
fi
if [ ! -x "${SDV_PY}/.venv/bin/python" ]; then
  echo "ERROR: no venv python at ${SDV_PY}/.venv/bin/python" >&2
  exit 2
fi

echo "host=$(hostname) SDV_PY=${SDV_PY} vendor=${NCAA_VENDOR}"
exec ./scripts/run_02_games.sh "$@"
