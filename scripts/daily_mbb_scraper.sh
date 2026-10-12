#!/usr/bin/env bash
# Daily in-season driver for NCAA MBB, run from the DROPLET CRONTAB.
# Composes the existing numbered stages (01 schedules -> 02 games capture ->
# 03 parse -> 04 rosters -> 05 datasets) -- it does NOT reimplement them, and
# a backfill is the same stages via run_mbb_backfill.sh, not a parallel impl.
#
# Season is END-year (2027 = 2026-27), same as hoopR-mbb-raw -- confirmed by
# reading the committed 2026 schedule's actual game dates (Nov 2025 -> Apr
# 2026). The season is derived from the date with the SAME rule as the
# downstream ncaa-mbb-hoops-data scripts/cron_publish_current.sh: August
# onward is next year's END-year season, so raw and data never disagree.
# NCAA's site opens the new season's crosswalk weeks after ESPN; a
# schedules 404/ValueError in Aug/Sep before then is expected, not a bug.
#
#   run:    NCAA_VENDOR=decodo_patchright ./scripts/daily_mbb_scraper.sh
#   watch:  tail -f logs/daily_mbb_$(date -u +%Y%m%d).log
#   check:  ./scripts/daily_mbb_scraper.sh --print-season   # resolve + exit, offline
#
# Tunables (env only -- never edit pace into the script):
#   MBB_SEASON         override the resolved season   (default: from date)
#   MBB_MAX_CONTESTS   per-run capture cap             (default 60, ~one
#                       night's worth of new games; run_02_games.sh's own
#                       "not yet captured" filter makes this safe to re-run)
#
# SAFE RATE: run_02_games.sh's own README governs -- 1 worker here, never
# --shard fan-out from a cron entry. NCAA_VENDOR must be set (decodo_patchright)
# for a cron context; the unset-vendor fallback in run_02_games.sh/
# run_04_rosters.sh demands ProxyBonanza creds from .Renviron, which a cron
# environment does not source.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

# END-year season from the (cron-local) date; Aug-Dec -> next year.
M=$((10#$(date +%m))); SEASON=$(date +%Y); [ "$M" -ge 8 ] && SEASON=$((SEASON + 1))
SEASON="${MBB_SEASON:-$SEASON}"
if [ "${1:-}" = "--print-season" ]; then echo "${SEASON}"; exit 0; fi

if [ -z "${NCAA_VENDOR:-}" ]; then
  echo "ERROR: NCAA_VENDOR must be set for a cron run (e.g. decodo_patchright)" >&2
  exit 2
fi
export SDV_PY="${SDV_PY:-/mnt/sdv_repos/sdv-py}"
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

# docs/SCRAPING_NOTES.md #5: the launchers import sportsdataverse from this
# WORKING TREE (PYTHONPATH), not a version pin -- a feature branch here
# silently runs unreviewed code against a hostile, ban-on-sight host. This
# already nearly re-ran an IP-burning version once.
sdv_py_branch="$(git -C "${SDV_PY}" branch --show-current 2>/dev/null || echo "?")"
if [ "${sdv_py_branch}" != "main" ]; then
  echo "ERROR: SDV_PY (${SDV_PY}) is on branch '${sdv_py_branch}', not main -- refusing to scrape" >&2
  exit 2
fi

MAX_CONTESTS="${MBB_MAX_CONTESTS:-60}"

LOG="logs/daily_mbb_$(date -u +%Y%m%d).log"
mkdir -p logs
{
  echo "[$(date -u '+%F %T')Z] daily mbb start: season=${SEASON} max=${MAX_CONTESTS} vendor=${NCAA_VENDOR}"
  rc_total=0

  bash scripts/run_01_schedules.sh --season "${SEASON}" || { echo "WARN schedules rc=$?"; rc_total=1; }
  bash scripts/run_02_games.sh --season "${SEASON}" --max-contests "${MAX_CONTESTS}" || { echo "WARN capture rc=$?"; rc_total=1; }
  bash scripts/run_03_parse.sh --season "${SEASON}" || { echo "WARN parse rc=$?"; rc_total=1; }
  bash scripts/run_04_rosters.sh --season "${SEASON}" || { echo "WARN rosters rc=$?"; rc_total=1; }
  bash scripts/run_05_datasets.sh --season "${SEASON}" || { echo "WARN datasets rc=$?"; rc_total=1; }
  # Stage 07 (J6) is non-fatal: a player-crosswalk miss must not fail the capture.
  bash scripts/run_07_player_xwalk.sh --seasons "${SEASON}" || echo "WARN player xwalk rc=$? (non-fatal)"

  echo "[$(date -u '+%F %T')Z] daily mbb stages done (rc_total=${rc_total})"
  exit "$rc_total"
} 2>&1 | tee -a "$LOG"
STAGE_RC="${PIPESTATUS[0]}"

# One commit for the whole night's output, via the repo's own commit helper
# (ONESHOT=1 SETTLE=0: capture already exited, nothing is mid-write).
SUBJECT="NCAA MBB Raw Update (Start: ${SEASON} End: ${SEASON})" ONESHOT=1 SETTLE=0 PUSH=1 \
  bash scripts/run_autocommit.sh || STAGE_RC=1

echo "[$(date -u '+%F %T')Z] daily mbb done EXIT=${STAGE_RC}" | tee -a "$LOG"
exit "$STAGE_RC"
