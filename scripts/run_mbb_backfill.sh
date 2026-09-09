#!/usr/bin/env bash
# One-command NCAA MBB backfill: discover -> capture -> parse, resumable.
#
# Chains the per-stage launchers (run_discover/run_capture/run_03_parse.sh) in order.
# RESUMABLE: capture skips already-captured contests; if it hard-stops on a ban,
# wait a while and just re-run this script -- it picks up where it left off.
# Parse is fully offline and safe to run on a partial capture.
#
# SAFE RATE: the old "1-2 workers, 4 => ban" figure was measured on the SHARED
# ProxyBonanza datacenter pool and is pool-relative, not absolute. With
# per-worker disjoint sticky residential ports it no longer binds -- see the
# WORKERS guard below for the current cap and its rationale.
# SESSION CEILING (measured 2026-07-13): a browser session captures cleanly for
# ~70min/~1400 bundles, then bm-verify stops clearing; the run degraded to ZERO
# yield for a full hour and earned a hard 403 at 2402/6300. So CHUNK it: capture
# ~1500, cool down, re-run. The capture loop now also self-aborts on a soft-ban
# (25 consecutive challenge failures) instead of hammering.
#
# Usage (run in YOUR terminal, on a residential IP -- stats.ncaa.org bans datacenter IPs):
#   ./scripts/run_mbb_backfill.sh 2026                      # 1 worker, unlimited
#   CHUNK=1500 ./scripts/run_mbb_backfill.sh 2026           # stop after 1500 new bundles (recommended)
#   WORKERS=2 CHUNK=1500 ./scripts/run_mbb_backfill.sh 2026 # 2 workers (measured ceiling)
#
# Watch live:  tail -f logs/backfill_<season>_<ts>.log   (path is printed on start;
#              per-stage logs under logs/ are also printed as each stage starts)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1          # -> ncaa-mbb-hoops-raw repo root
ROOT="$(pwd)"
SDV_PY="${SDV_PY:-C:/Users/saiem/Documents/GitHub-Data/sdv-dev/sdv-py}"
# .venv layout is OS-dependent: Linux/droplet = .venv/bin, Windows = .venv/Scripts
if [ -x "${SDV_PY}/.venv/bin/python" ]; then PY="${PY:-${SDV_PY}/.venv/bin/python}"
else PY="${PY:-${SDV_PY}/.venv/Scripts/python.exe}"; fi

SEASON="${1:?usage: run_mbb_backfill.sh <season>  (ending year, e.g. 2026)}"

# SEASON RANGE: MIN/MAX_SEASON track the bundled MBB crosswalk
# (sportsdataverse/mbb/data/ncaa_teamids_mbb.csv), which covers 2009-10..2025-26.
# Refusing here gives the real cause; without it discover_season() raises its
# generic "crosswalk drift" ValueError and the operator debugs the wrong thing.
# Ported from the WBB twin, where a STALE ceiling (MAX_SEASON=2025 after the
# crosswalk already covered 2026) refused a valid season with rc=2, the range
# driver read that as a capture hard-stop, and the 2026-08-01 campaign captured
# ZERO bundles while discovery looked healthy. **Bump MAX_SEASON in the same
# change as the crosswalk season** -- a stale guard does not fail loudly, it
# burns a campaign.
MIN_SEASON=2010
MAX_SEASON=2026
case "$SEASON" in
  ''|*[!0-9]*)
    echo "REFUSING SEASON='${SEASON}' -- must be a plain integer ending year (e.g. 2026)." >&2
    exit 2 ;;
esac
if [ "$SEASON" -lt "$MIN_SEASON" ]; then
  echo "REFUSING season=${SEASON} -- the bundled MBB crosswalk (sportsdataverse/mbb/data/ncaa_teamids_mbb.csv)" >&2
  echo "  starts at season ${MIN_SEASON} (2009-10); there is no earlier row." >&2
  exit 2
fi
if [ "$SEASON" -gt "$MAX_SEASON" ]; then
  echo "REFUSING season=${SEASON} -- the bundled MBB crosswalk (sportsdataverse/mbb/data/ncaa_teamids_mbb.csv)" >&2
  echo "  only covers seasons through ${MAX_SEASON}; there is no later row yet." >&2
  echo "  This is a crosswalk coverage gap, not the 'team-ids format drift' that discover_season()" >&2
  echo "  would otherwise report. Extending the crosswalk is a separate sdv-py change; once it" >&2
  echo "  lands, bump MAX_SEASON in this script." >&2
  exit 2
fi

WORKERS="${WORKERS:-1}"
# Ceiling history: 2 was measured on the shared ProxyBonanza datacenter pool
# (4 workers piled onto few IPs => ban). With per-worker DISJOINT sticky
# residential ports (decodo us.decodo.com:10001-10050, sharded by worker index
# in _vendor_fetcher), 8 and 16 have both run clean -- the limit that matters
# is per-IP pacing, not process count. Cap at 24: the pool is 50 ports, so 24
# still leaves ~2 ports per worker, and per-IP rate stays far under the ~20
# pages/min that measured safe on a SINGLE ip. Going past ~25 would put more
# than one worker on an ip at a time, which is the pattern that actually bans.
#
# WHY THE CEILING MATTERS BEYOND THROUGHPUT: capture.shard() splits a season by
# `k % n`, so a campaign that loses one shard leaves a stride-n residual. A
# re-run with m workers lands it on m/gcd(n,m) shards -- a coprime m spreads it
# across ALL m, a shared factor concentrates it (worst case, onto one worker).
# On 2026-08-11 the fix was WORKERS=23, coprime to the 24 that left the gap,
# taking the deepest shard from 172 fetches to 9 and the rate from 3/min to
# 34.6/min. A ceiling below 23 forces a value sharing a factor with 24.
# See docs/SCRAPING_NOTES.md 2026-08-11.
#
# Numeric form (not a `case` glob) so it matches the WBB twin exactly and so a
# leading-zero value like 023 is read as 23 rather than refused.
case "$WORKERS" in
  ''|*[!0-9]*) WORKERS=0 ;;
esac
if [ "$WORKERS" -lt 1 ] || [ "$WORKERS" -gt 24 ]; then
  echo "REFUSING WORKERS='${WORKERS}' -- must be 1..24 (each worker rides its own" >&2
  echo "  disjoint sticky proxy session; pool is 50 ports, keep >=2 per worker)." >&2
  exit 2
fi

mkdir -p logs
TS="$(date +%Y%m%d_%H%M%S)"
LOG="logs/backfill_${SEASON}_${TS}.log"
say() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

say "NCAA MBB backfill: season=${SEASON} workers=${WORKERS}"
say "watch this run:  tail -f ${ROOT}/${LOG}"

# --- 1) discover: only if this season has no rows yet (avoid re-scraping team pages) ---
need_discover() {
  [ -f mbb/schedule_master.parquet ] || return 0
  local n
  n="$("$PY" -c "import polars as pl; print(pl.read_parquet('mbb/schedule_master.parquet').filter(pl.col('season')==str(${SEASON})).height)" 2>/dev/null || echo 0)"
  [ "${n:-0}" -eq 0 ]
}
if need_discover; then
  say "=== discover ${SEASON} (season not in schedule_master yet) ==="
  ./scripts/run_01_schedules.sh --season "$SEASON" || { say "discover FAILED -- stopping (fix creds/network, then re-run)"; exit 1; }
else
  say "=== skip discover (season ${SEASON} already in schedule_master; delete mbb/schedule_master.parquet to force) ==="
fi

# --- 2) capture (resumable, ban-hard-stops). 1 shard, or WORKERS disjoint shards in parallel. ---
CAP_ARGS=(--season "$SEASON")
if [ -n "${CHUNK:-}" ]; then
  CAP_ARGS+=(--max-contests "$CHUNK")
  say "=== capture ${SEASON}: ${WORKERS} worker(s), chunk=${CHUNK} new bundles per worker ==="
else
  say "=== capture ${SEASON} with ${WORKERS} worker(s) (no chunk limit) ==="
fi
rc=0
if [ "$WORKERS" -eq 1 ]; then
  ./scripts/run_02_games.sh "${CAP_ARGS[@]}" --shard 0/1 || rc=$?
else
  pids=()
  for i in $(seq 0 $((WORKERS-1))); do
    ./scripts/run_02_games.sh "${CAP_ARGS[@]}" --shard "${i}/${WORKERS}" &
    pids+=($!)
  done
  for p in "${pids[@]}"; do wait "$p" || rc=$?; done
fi
if [ "$rc" -ne 0 ]; then
  say "capture stopped (rc=${rc}) -- a ban/soft-ban hard-stop or Ctrl-C (see the capture log)."
  say "  This is RESUMABLE: cool down (a ban clears in minutes-hours), then re-run this"
  say "  script -- already-captured contests are skipped."
fi

# --- 3) parse (offline; safe on a partial capture) -> mbb/json/{contest_id}.json ---
say "=== parse captured bundles -> mbb/json/ ==="
./scripts/run_03_parse.sh --league mbb || { say "parse FAILED"; exit 1; }

# --- summary + next step ---
CAP="$(find mbb/raw -name '*.json.gz' 2>/dev/null | wc -l | tr -d ' ')"
JSON="$(ls mbb/json 2>/dev/null | wc -l | tr -d ' ')"
say "DONE: captured_bundles=${CAP} parsed_json=${JSON} (capture rc=${rc})"
if [ "$rc" -eq 0 ]; then
  say "next -> build the -data parquet:"
  say "  cd ${ROOT}/../ncaa-mbb-hoops-data && python -m ncaa_mbb_data_build build --dataset all --season ${SEASON}"
else
  say "capture INCOMPLETE (rc=${rc}) -- re-run this script to continue before building."
fi
echo "EXIT=${rc}" | tee -a "$LOG"
exit "$rc"
