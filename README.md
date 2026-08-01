# ncaa-mbb-hoops-raw
NCAA MBB Raw Data

Raw-page capture + parse pipeline for `stats.ncaa.org` men's college
basketball. Three stages: **discover** (season -> contest_ids) -> **capture**
(contest -> 3-page HTML bundle) -> **parse** (bundle -> combined per-game
JSON). Data tree lives under `<root>/mbb/` (default root = repo root):
`schedule_master.parquet`, `raw/{season}/{contest_id}.json.gz`,
`json/{contest_id}.json`.

Three further committed datasets — **schedules**, **teams**, **rosters** — ride
along for free. `discover` already fetches every team's schedule page and
`rosters` already fetches every roster page, so both trees are persisted from
those existing fetches at **zero extra HTTP**; `teams` needs no fetch at all
(it is the bundled sdv-py crosswalk). Per team the source `html` and the parsed
`json` are kept; `parquet` is the one compiled dataset per season:

```
mbb/schedules/html/{season}/{team_id}.html     mbb/rosters/html/{season}/{team_id}.html
mbb/schedules/json/{season}/{team_id}.json     mbb/rosters/json/{season}/{team_id}.json
mbb/schedules/parquet/{season}.parquet         mbb/rosters/parquet/{season}.parquet
mbb/teams/{html,json,parquet}/{season}.*
```

Every one of them carries human-readable names next to the machine ids —
schedules pair `team_id`/`opponent_id` with `team`/`opponent`, rosters pair
`player_id` with `clean_name` (display form) *and* `player` (the ALL-CAPS
`FIRST.LAST` play-by-play join key), teams pair `ncaa_team_id` with the NCAA
name, conference and `division` (constant `"I"` — the crosswalk is scoped to
the Division-I `season_divisions` id).

## Setup

Requires the sibling `sdv-py` checkout at
`C:/Users/saiem/Documents/GitHub-Data/sdv-dev/sdv-py` with its `.venv`
synced (`uv sync --all-extras --dev` there). Discover + capture also need
ProxyBonanza creds in `~/.Renviron` (or `~/Documents/.Renviron`):

```
PROXYBONANZA_API_KEY=...
PROXY_PKG=...
```

The launchers read these at call time and never print or persist the raw
values. `parse` is fully offline and needs no creds.

## Run order

```sh
bash scripts/run_discover.sh --season 2026     # -> mbb/schedule_master.parquet (~5.5-6k contest_ids)
                                               #    + mbb/schedules/{html,json}/2026/
bash scripts/run_capture.sh  --season 2026     # -> mbb/raw/2026/{contest_id}.json.gz
bash scripts/run_parse.sh                      # -> mbb/json/{contest_id}.json
bash scripts/run_rosters.sh  --season 2026     # -> mbb/rosters/{html,json}/2026/
bash scripts/run_datasets.sh --season 2026     # -> the season parquets + mbb/teams/
```

`run_datasets.sh` is fully offline (no creds, no network) and **not sharded**:
each season parquet is a single output file, so concurrent `--shard` workers
would race it. Run it once, after the sharded sweeps finish. It also re-derives
any missing per-team json from committed html, so a parser fix can be replayed
across every captured season with `--overwrite` and no re-scrape.

Watch a running job live:

```sh
tail -f logs/capture_*.log
```

## Safe-rate rule (capture)

**1-2 workers max, ever.** Each worker is a *separate process* running
`run_capture.sh` with a disjoint `--shard i/N` -- never threads inside one
process, never 4+ processes:

```sh
./scripts/run_capture.sh --season 2026                    # 1 worker (proven-safe default, ~6h)
./scripts/run_capture.sh --season 2026 --shard 0/2 &       # 2 workers (~4h), only after 1-worker is stable
./scripts/run_capture.sh --season 2026 --shard 1/2 &
```

A ban-suspect response is a **hard stop**, not a retry: the process exits
immediately (`BAN-SUSPECT: capture halted at contest_id=...`). Wait out the
cooldown before resuming -- do not immediately re-launch.

⚠️ On a persistent ban, the upstream `NcaaFetcher` retries across the entire
residential proxy pool with no delay before raising -- so a single
ban-detection can send a ~pool-sized burst before the scraper hard-stops.
This is bounded (the run terminates), but re-running immediately into a live
ban will re-churn the pool. On a `BAN-SUSPECT` stop, WAIT for a multi-minute
cooldown before resuming. (Follow-up: add inter-rotation backoff upstream in
sdv-py.)

## Resume story

Every stage is idempotent and re-runnable:

- **discover** merges new contest_ids into the existing `schedule_master.parquet`
  without touching rows already `captured=True`.
- **capture** only fetches contest_ids where `captured==False` in the master
  file; re-running after a ban-suspect stop (or a plain interruption) picks up
  where it left off.
- **parse** skips any contest_id that already has a `mbb/json/{contest_id}.json`
  output; re-running only parses newly captured bundles.

So `bash scripts/run_discover.sh --season 2026 && bash scripts/run_capture.sh --season 2026 && bash scripts/run_parse.sh`
is safe to re-run wholesale after any interruption.
