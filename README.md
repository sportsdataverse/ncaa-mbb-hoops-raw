# ncaa-mbb-hoops-raw
NCAA MBB Raw Data

Raw-page capture + parse pipeline for `stats.ncaa.org` men's college
basketball. Three stages: **discover** (season -> contest_ids) -> **capture**
(contest -> 3-page HTML bundle) -> **parse** (bundle -> combined per-game
JSON). Data tree lives under `<root>/mbb/` (default root = repo root):
`schedule_master.parquet`, `raw/{season}/{contest_id}.json.gz`,
`json/{contest_id}.json`.

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
bash scripts/run_capture.sh  --season 2026     # -> mbb/raw/2026/{contest_id}.json.gz
bash scripts/run_parse.sh                      # -> mbb/json/{contest_id}.json
```

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
