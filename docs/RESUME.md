# Resume the NCAA basketball backfill

State as of **2026-08-11 22:10 EDT**, verified by an on-disk census after the
2017-2012 recovery run. Everything below is committed and pushed; nothing is
running.

Trust the census, not a previous edition of this file: the edition before this
one was ~9 days stale and claimed 56% complete with "2016..2010 not started",
all false by the time anyone read it.

Read `docs/SCRAPING_NOTES.md` first — it is the canonical operational
reference for stats.ncaa.org, and it supersedes this file wherever they
disagree about transport.

## Where it stopped

State verified by on-disk census **2026-08-11 22:10 EDT**. Nothing is running.

**The 2026-08-11 run closed the 2017-2012 residual**: +692 contests captured in
~50 minutes of wall clock. MBB pbp capture is now **99,932 / 100,037 (99.895%)**,
every captured bundle parsed (`mbb/json/` count == `mbb/raw/` count).

| season | captured | in master | gap | note |
| --- | ---: | ---: | ---: | --- |
| 2026 | 6297 | 6300 | 3 | pageless |
| 2025 | 6293 | 6293 | 0 | complete |
| 2024 | 6243 | 6243 | 0 | complete |
| 2023 | 6221 | 6222 | 1 | pageless |
| 2022 | 5970 | 5971 | 1 | pageless |
| 2021 | 4269 | 4286 | 17 | pageless |
| 2020 | 5783 | 5783 | 0 | complete |
| 2019 | 6040 | 6042 | 2 | pageless |
| 2018 | 6002 | 6003 | 1 | pageless |
| 2017 | 5971 | 5972 | 1 | **+104 on 08-11** |
| 2016 | 5949 | 5950 | 1 | **+241 on 08-11** |
| 2015 | 5927 | 5932 | 5 | +0 (no page) |
| 2014 | 5946 | 5947 | 1 | +0 (no page) |
| 2013 | 5809 | 5814 | 5 | **+184 on 08-11** |
| 2012 | 5763 | 5775 | 12 | **+163 on 08-11** |
| 2011 | 5737 | 5749 | 12 | NOT yet re-run |
| 2010 | 5712 | 5755 | 43 | NOT yet re-run |
| **TOTAL** | **99932** | **100037** | **105** | |

### What the remaining 105 are

- **55 in 2010-2011**, untouched tonight because the run was scoped 2017-2012.
  **These are the next real work** — and they are very likely the same dead-shard
  residual, so re-run them with the coprime-WORKERS rule below, not with 8/24.
- **25 pageless** in 2018-2026, documented before this campaign.
- **25 across 2012-2017** after tonight's sweep. Each season converged to a
  handful and stopped yielding, which is the signature of contests with no game
  page rather than blocked ones.

### The correction this run forced

The 711 contests the August campaign abandoned at `MAX_ROUNDS` were **never
"un-capturable"** — 692 of them captured cleanly tonight against the same site
with a healthy vendor. They were **one dead worker-shard**, re-serialized onto a
single worker by every retry (see the coprime-WORKERS rule below and
SCRAPING_NOTES 2026-08-11). Do not read a `MAX_ROUNDS` abandonment, or a
straggler-guard "un-capturable" label, as evidence a contest has no page.

WBB pbp capture: **0 games** (never started). Its reference data is complete.
See the WBB twin's own docs before starting it.

## Reference data — COMPLETE, both leagues

`{lg}/schedules/`, `{lg}/rosters/`, `{lg}/teams/` in html + json + parquet:
MBB 17 seasons (2010-2026), WBB 16 (2011-2026). Per-team html+json, one
compiled parquet per season. Built with ZERO extra HTTP — discovery already
fetched team pages and the roster stage already fetched roster pages.

Also complete: `{lg}/xwalk/espn_game_id/` (contest_id -> ESPN event id), and
the NCAA<->ESPN **team** crosswalk which lives in sdv-py (merged, PR #314).

## Before you launch — three preconditions

1. **Decodo IPs only.** Binding user directive (2026-08-11): this family runs
   on our Decodo pool and nothing else. Set `VENDOR` to a `decodo_*` entry (the
   range driver re-exports it as `NCAA_VENDOR` per season). The other entries
   in `canary_vendors.toml` (netnut, zyte, brightdata) are unconfigured and the
   canary skips them today — if anyone fills their creds later, they still must
   not be used here.

   The one path that can leave Decodo: `run_01_schedules.sh` (discover) falls
   back to **ProxyBonanza** creds read from `~/.Renviron` when `NCAA_VENDOR` is
   empty. Always launch with `VENDOR` set. Re-running 2017–2012 does not
   re-discover — every season is already in `schedule_master` — so discover
   should not fetch at all here.

2. **Canary first, and it actually works again now.** `run_98_canary.sh` was a
   **silent no-op from 2026-08-02 until 2026-08-11**: the engine extraction
   dropped the shim's `__main__` block, so the driver ran a module that defined
   some names, exited 0, and probed nothing. That covered the entire
   2026-08-02→08-05 campaign — the one that hit ban after ban with no working
   way to score a vendor. Fixed, with regression checks, in the stage-numbering
   change. Run it before scaling up (SCRAPING_NOTES §5.2).

3. **Know which sdv-py the launchers will import.** They put the sdv-py
   *working tree* on `PYTHONPATH` — not a version pin — so whatever branch that
   checkout sits on is the code that runs (SCRAPING_NOTES §5.5). Verified
   2026-08-11: `sportsdataverse/scrape/ncaa/` is **byte-identical between
   `feat/crosswalk-prereqs` and `origin/main`**, so a run from that branch is
   safe today. Re-check with
   `git -C ../../sdv-py diff --stat HEAD origin/main -- sportsdataverse/scrape/ncaa/`
   (empty output = safe) rather than assuming either way.

## To resume — the 55 left in 2011-2010

```sh
cd C:/Users/saiem/Documents/GitHub-Data/sdv-dev/hoopR-dev/ncaa-mbb-hoops-raw

# 0. pre-flight: score the Decodo vendors, pick the healthiest (10 games x 2 pages)
bash scripts/run_98_canary.sh --games 10
#    -> canary_out/canary_<ts>.md ; PASS = >=90% clean

# 1. the two seasons never re-run, newest-first. Resume is free: capture skips
#    every contest already on disk, so the ~11.4k already-captured games in
#    this range cost a file-exists check each, not a fetch.
#    NOTE the knob is VENDOR, not NCAA_VENDOR: the range driver exports
#    NCAA_VENDOR="$VENDOR" to each season, so an outer NCAA_VENDOR is
#    OVERRIDDEN. (VENDOR already defaults to decodo_patchright; set it
#    explicitly anyway so the Decodo-only rule is visible in the command.)
#
#    WORKERS=23 IS DELIBERATE, NOT A TYPO. The August run used 24 workers and
#    lost a shard, so its residual sits at positions k = r (mod 24) and any
#    WORKERS sharing a factor with 24 (8/12/16/24) hands the whole block back
#    to ONE worker -- measured 172 fetches deep vs 9 at 23. Coprime wins:
#    3 captures/min -> 34.6/min. See SCRAPING_NOTES 2026-08-11.
#    RE-CHECK THE SHARD MATH FOR 2011/2010 before launching (snippet in
#    SCRAPING_NOTES): their residual may have a different stride than 24.
VENDOR=decodo_patchright \
WORKERS=23 CHUNK=400 PARSE_WORKERS=16 MAX_ROUNDS=12 \
  nohup bash scripts/run_mbb_backfill_range.sh 2011 2010 >> logs/campaign.log 2>&1 &

# 2. ALWAYS start this too -- the campaign commits NOTHING itself
nohup bash scripts/run_autocommit.sh >> logs/autocommit_nohup.log 2>&1 &
```

Watch it live (either form):

```sh
tail -f logs/backfill_range_*.log
powershell -Command "Get-Content -Path logs/campaign.log -Tail 5 -Wait"
```

Ctrl-C is always safe — the disk is the checkpoint, so a restart picks up
exactly where it stopped. `EXIT=` lines mark each stage's real exit code; a
`hard-stopped (rc=1)` line means the vendor is being refused, so re-canary
before pushing further rather than burning rounds on cooldowns (that is how
these four seasons were lost the first time).

Budget ~5 minutes of fixed overhead per season even when there is nothing to
fetch: 23 workers still scan every contest id for file existence, then a parse
sweep runs, then the straggler round repeats both. On 2026-08-11 that overhead,
not the fetching, was most of the wall clock once the shards were balanced.

**Kill leftover workers between runs.** Capture workers from a finished season
were found still alive 45 minutes later, holding proxy sessions and competing
with the current round for the port pool. Check for python processes older than
the current season's start time and stop those by PID.

## Known wrinkles (not blockers)

- `schedule_master`'s `captured` column is **vestigial** — 92,943 rows sit on
  disk still flagged `false` (only 2026's 6,297 are `true`). Resume is
  file-exists based, so this is harmless for capture, but do not read that
  column to answer "what do we have".
- The master is still `mbb/schedule_master.parquet`; the D33 writer-side rename
  to `mbb/mbb_schedule_master.parquet` is an open follow-up (the `-data` twins
  already read both names, new first).
- The eight `scripts/run_*.sh` drivers execute the **sibling sdv-py repo's**
  venv via a hardcoded absolute path, not this repo's `.venv` — so a live run
  does not use the `sportsdataverse` pin that `uv sync --frozen` and CI
  enforce. Deliberate for now (this repo's own venv is not proven to carry the
  transport extras); see the template's `scripts/_venv.sh` for the fix.
