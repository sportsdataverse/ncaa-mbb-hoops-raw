# Resume the NCAA basketball backfill

State as of **2026-08-11 19:15 EDT**, verified by an on-disk census (not by
reading the previous edition of this file — it was ~9 days stale and claimed
56% complete with "2016..2010 not started", all of which was false by then).
Everything below is committed and pushed; nothing is running.

Read `docs/SCRAPING_NOTES.md` first — it is the canonical operational
reference for stats.ncaa.org, and it supersedes this file wherever they
disagree about transport.

## Where it stopped

The last campaign ran **2026-08-02 14:02 → 2026-08-05 14:40** (range 2017→2010)
and ended with `campaign finished 2017..2010`. That line means the driver
walked the whole season range — **not** that every season completed. Four
seasons were abandoned mid-recovery at the round cap.

MBB pbp capture: **99,240 / 100,037 contests (99.2%)**, and every captured
bundle is parsed (`mbb/json/` count == `mbb/raw/` count, parse reports
`pending=0`).

| season | captured | in master | gap | terminal state |
| --- | ---: | ---: | ---: | --- |
| 2026 | 6297 | 6300 | 3 | complete (pageless) |
| 2025 | 6293 | 6293 | 0 | complete |
| 2024 | 6243 | 6243 | 0 | complete |
| 2023 | 6221 | 6222 | 1 | complete (pageless) |
| 2022 | 5970 | 5971 | 1 | complete (pageless) |
| 2021 | 4269 | 4286 | 17 | complete (pageless) |
| 2020 | 5783 | 5783 | 0 | complete |
| 2019 | 6040 | 6042 | 2 | complete (pageless) |
| 2018 | 6002 | 6003 | 1 | complete (pageless) |
| **2017** | **5867** | 5972 | **105** | **MAX_ROUNDS=12 — "re-run later to finish"** |
| **2016** | **5708** | 5950 | **242** | **MAX_ROUNDS=12 — "re-run later to finish"** |
| 2015 | 5927 | 5932 | 5 | straggler guard: a round captured nothing |
| 2014 | 5946 | 5947 | 1 | straggler guard: a round captured nothing |
| **2013** | **5625** | 5814 | **189** | **MAX_ROUNDS=12 — "re-run later to finish"** |
| **2012** | **5600** | 5775 | **175** | **MAX_ROUNDS=12 — "re-run later to finish"** |
| 2011 | 5737 | 5749 | 12 | straggler guard: a round captured nothing |
| 2010 | 5712 | 5755 | 43 | straggler guard: a round captured nothing |
| **TOTAL** | **99240** | **100037** | **797** | |

The 797 missing contests are three different things, and only the first group
is known to be worth re-running:

- **711 abandoned at the round cap** (2016 242, 2013 189, 2012 175, 2017 105).
  The driver's own message is `MAX_ROUNDS=12 reached with N remaining -- moving
  on (re-run later to finish)`. Their rounds ended `chunk N hard-stopped
  (rc=1) ... cooling 1800s` — the run was being refused, so these were never
  shown to be uncapturable. **This is the work to pick up.**
- **61 exhausted by the straggler guard** (2010 43, 2011 12, 2015 5, 2014 1).
  The guard exits a season when a whole round captures nothing and labels the
  remainder "un-capturable". That is a heuristic, **not** proof the pages don't
  exist — see the warning below.
- **25 pageless**, documented before this campaign (2021 17, 2026 3, 2019 2,
  and one each in 2018 / 2022 / 2023). Contests in `schedule_master` with no
  game page on stats.ncaa.org; they will never capture.

> ⚠️ **Do not classify the residual from the log's `challenge not cleared`
> lines.** That warning fires for ANY page failing `_is_clean` — a thin Akamai
> stub and a legitimately absent page produce the same message. SCRAPING_NOTES
> §2 and §8 record that trusting this line sent three successive diagnoses the
> wrong way. Only 92 distinct contest ids ever emitted it. To settle
> pageless-vs-blocked, dump the actual bytes (status, length, first 300 chars)
> for a sample — nobody has done that for these 797.

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

## To resume — the 711

```sh
cd C:/Users/saiem/Documents/GitHub-Data/sdv-dev/hoopR-dev/ncaa-mbb-hoops-raw

# 0. pre-flight: score the Decodo vendors, pick the healthiest (10 games x 2 pages)
bash scripts/run_98_canary.sh --games 10
#    -> canary_out/canary_<ts>.md ; PASS = >=90% clean

# 1. the four unfinished seasons, newest-first. Resume is free: capture skips
#    every contest already on disk, so the ~23k already-captured games in this
#    range cost a file-exists check each, not a fetch.
#    NOTE the knob is VENDOR, not NCAA_VENDOR: the range driver exports
#    NCAA_VENDOR="$VENDOR" to each season, so an outer NCAA_VENDOR is
#    OVERRIDDEN. (VENDOR already defaults to decodo_patchright; set it
#    explicitly anyway so the Decodo-only rule is visible in the command.)
VENDOR=decodo_patchright \
WORKERS=8 CHUNK=400 PARSE_WORKERS=12 MAX_ROUNDS=12 \
  nohup bash scripts/run_mbb_backfill_range.sh 2017 2012 >> logs/campaign.log 2>&1 &

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

Note that 2015 and 2014 sit inside the 2017→2012 range and have only 6
outstanding contests between them; they cost one quick skip-pass each.

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
