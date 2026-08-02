# Resume the NCAA basketball backfill

State as of **2026-08-02 13:46 EDT**. Everything below is committed and pushed;
nothing is running. Read `docs/SCRAPING_NOTES.md` first — it is the canonical
operational reference for stats.ncaa.org.

## Where it stopped

MBB pbp capture: **56,039 / 100,037 games (56.0%)**

| season | captured | target | state |
|---|---:|---:|---|
| 2026 | 6297 | 6300 | complete (3 pageless) |
| 2025 | 6293 | 6293 | complete |
| 2024 | 6243 | 6243 | complete |
| 2023 | 6221 | 6222 | complete (1 pageless) |
| 2022 | 5970 | 5971 | complete (1 pageless) |
| 2021 | 4269 | 4286 | complete (17 pageless) |
| 2020 | 5783 | 5783 | complete |
| 2019 | 6040 | 6042 | complete (2 pageless) |
| 2018 | 6002 | 6003 | complete (1 pageless) |
| **2017** | **2921** | **5972** | **IN PROGRESS — resume here** |
| 2016..2010 | 0 | ~41,100 | not started |

"pageless" = the contest is in `schedule_master` but has no game page on
stats.ncaa.org and never will. The campaign's straggler guard exits a season
on the first round that captures nothing, so these do not stall it.

WBB pbp capture: **0 games** (never started; stopped before its first season by
request). Its reference data is complete.

## Reference data — COMPLETE, both leagues

`{lg}/schedules/`, `{lg}/rosters/`, `{lg}/teams/` in html + json + parquet:
MBB 17 seasons (2010-2026), WBB 16 (2011-2026). Per-team html+json, one
compiled parquet per season. Built with ZERO extra HTTP — discovery already
fetched team pages and the roster stage already fetched roster pages.

Also complete: `{lg}/xwalk/espn_game_id/` (contest_id -> ESPN event id), and
the NCAA<->ESPN **team** crosswalk which lives in sdv-py (merged, PR #314).

## To resume

```sh
cd C:/Users/saiem/Documents/GitHub-Data/sdv-dev/hoopR-dev/ncaa-mbb-hoops-raw

# 1. the capture campaign (resumes mid-2017 automatically -- disk is the checkpoint)
WORKERS=24 CHUNK=400 DISCOVER_WORKERS=24 PARSE_WORKERS=24 \
  nohup bash scripts/run_mbb_backfill_range.sh 2017 2010 >> logs/campaign.log 2>&1 &

# 2. ALWAYS start this too -- the campaign does NOT commit anything itself
nohup bash scripts/run_autocommit.sh >> logs/autocommit_nohup.log 2>&1 &

# watch
tail -f logs/backfill_range_*.log
```

WBB is identical with `run_wbb_backfill_range.sh 2026 2011` from the wbb repo.

Estimated remaining: MBB ~17h at 24 workers (~45 games/min). WBB ~35h from zero.

## Hard-won gotchas (do not rediscover these)

- **The campaign never commits.** `run_autocommit.sh` must run alongside it or
  ~12.5k files/season pile up untracked. It stages only files whose mtime has
  settled (>1min) so an in-flight bundle is never committed half-written.
- **Never edit a running bash script** — bash re-reads it at a stale byte
  offset and dies with a syntax error mid-run. Stop, edit, relaunch. Python
  module edits ARE safe (imported once at process start).
- **Killing by CommandLine pattern kills your own shell** if the pattern
  appears in your own command line. Walk the PID ancestor chain and exclude it.
- **A worker count of 0 does not mean the campaign died** — check the log's
  `=== season NNNN ===` markers. Between seasons there is a real lull.
- **`WORKERS` cap is 24** (guard in `run_mbb_backfill.sh`). The pool is 50
  sticky residential ports; past ~25 two workers share an ip, which is the
  pattern that actually earns a ban. The old "1-2 workers" figure was measured
  on the retired datacenter pool and is not a real ceiling.
- **Python needs Windows-style paths** (`C:/...`). A Git-Bash `/c/...` path
  silently fails — and for `NCAA_MBB_RAW_ROOT` it yields 0-row builds with no
  error. It must also be the checkout ROOT, not `.../mbb`.

## Open work, in priority order

1. **Corpus re-parse.** The ~56k already-parsed games predate the final schema.
   Re-parsing applies `contest_id` everywhere (replacing `game_id`, and fixing
   `shots` whose id was hardcoded `None`), ESPN game+team ids, and the ten
   on-court player id/name columns. Do it AFTER capture finishes so it sweeps
   once. Per-season commit+push — one shot would be a multi-GB push.
   `ncaa_parse.py` needs `--overwrite`/`--season` flags first; it currently
   skips any game whose json exists.
2. **WBB pbp capture** — ~93k games, 16 seasons, reference data ready.
3. Enrichment size is **1.678x** base json. Dropping the ten on-court
   `clean_name` columns (keeping their ids) gets ~1.40x; user chose to keep.
