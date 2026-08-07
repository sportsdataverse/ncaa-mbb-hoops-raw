# CLAUDE.md — ncaa-mbb-hoops-raw Development Guide

## Package Overview

This repo is the **raw-page capture + parse stage** for `stats.ncaa.org`
men's college basketball. It scrapes; it does not reshape.

Pipeline: `stats.ncaa.org -> ncaa-mbb-hoops-raw [HERE] -> ncaa-mbb-hoops-data
-> sportsdataverse-data`.

Three stages, in order:

1. **discover** — season -> `contest_id`s (`mbb/mbb_schedule_master.parquet`
   plus `mbb/schedules/{html,json}/{season}/`).
2. **capture** — contest -> a 3-page HTML bundle at
   `mbb/raw/{season}/{contest_id}.json.gz`.
3. **parse** — bundle -> combined per-game JSON at `mbb/json/{contest_id}.json`.

`README.md` is the operator-facing runbook (run order, safe-rate rules, resume
story). This file is the agent-facing companion — read both.

> **REQUIRED READING before any live `stats.ncaa.org` scrape:
> [`docs/SCRAPING_NOTES.md`](docs/SCRAPING_NOTES.md).** stats.ncaa.org is a
> hostile host — patchright + a residential proxy port pool, a ~70-minute
> sticky-session ceiling, and a bm-verify solve flow. The notes carry the
> access model, the response-class taxonomy that "broke us", measured
> campaign behavior, and the operational rules. Do **not** start a capture
> from intuition. `docs/RESUME.md` carries the campaign resume state.

**The `-raw` / `-data` split is load-bearing: never mix them.** This repo
scrapes and parses only. Reshaping parsed JSON into tidy season datasets is
`ncaa-mbb-hoops-data`'s job. A fix to a *tidy dataset* belongs there; a fix to
*capture or parsing* belongs here — or upstream in sdv-py (see below).

## Layout

```
python/       # flat ncaa_* modules, run by path (NOT an installable package)
  ncaa_discover.py  ncaa_capture.py  ncaa_parse.py  ncaa_bundle.py
  ncaa_datasets.py  ncaa_rosters.py  ncaa_identity.py
  ncaa_canary.py    ncaa_espn_game_xwalk.py
scripts/      # bash drivers (see below)
tests/        # suite + fixtures/ at repo ROOT, not under python/
docs/         # SCRAPING_NOTES.md (required reading), RESUME.md
logs/         # run logs (no longer gitignored — D22)
mbb/          # the committed capture tree; see README.md
```

The `python/` modules are **shims over `sportsdataverse.scrape.ncaa`**, the
shared NCAA hoops engine (sdv-py #328/#330/#331). Fix transport, fetcher, and
parser bugs **upstream in sdv-py**, not inline here — the WBB twin
(`wehoop-dev/ncaa-wbb-hoops-raw`) shares that engine, so an inline fix here
only half-fixes the problem.

### scripts/

Per-stage: `run_discover.sh`, `run_capture.sh`, `run_parse.sh`,
`run_rosters.sh`, `run_datasets.sh`.

Wrappers: `run_canary.sh` (pre-flight proxy-vendor scorecard),
`run_mbb_backfill.sh` (single-season discover->capture->parse chain),
`run_mbb_backfill_range.sh` (multi-season campaign wrapping it),
`run_reference_backfill.sh` (reference-only companion; no pbp capture),
`run_autocommit.sh` (settle-aware incremental commit sweep, safe to run
concurrently with an active capture).

`.github/workflows/orphan_scripts.yml` runs the shared
`sportsdataverse/.github` gate: **every** entry in `scripts/` must be
referenced by a runbook, a workflow, or another script. Adding a script means
also referencing it (here or in `README.md`).

## Packaging

Root `pyproject.toml` + `uv.lock`. **There is no `requirements.txt`.**

- `sportsdataverse` is pinned to git `main` via `[tool.uv.sources]` — the NCAA
  engine lands on main ahead of PyPI. CI installs with `uv sync --frozen`, so
  the lockfile is the contract.
- `[tool.uv] package = false` — `python/` holds flat modules run by path, not
  an installable package.
- pytest: `testpaths = ["tests"]`, `pythonpath = ["python"]`, and an
  **`archive` marker** for tests that need the full committed `mbb/` tree.
  CI deselects them (`-m "not archive"`) because it sparse-checks out code only.
- ruff: `line-length = 100`, rule set pinned to `select = ["E4","E7","E9","F","I"]`,
  `ignore = ["E712"]` (polars bool masks are written `pl.col("c") == True` on
  purpose). The pin is deliberate — ruff's defaults shift between versions and
  can turn a green tree red with no code change.

```sh
uv sync --frozen
uv run pytest -q -m "not archive"
uv run ruff check python/ tests/
```

## CI

Two workflows, both offline:

- `.github/workflows/tests.yml` — sparse-checkout (`python`, `tests`,
  `scripts`, `pyproject.toml`, `uv.lock`; the `mbb/` tree is ~175k files the
  tests never read and a full checkout never finishes), then
  `uv sync --frozen` -> `ruff check python/ tests/` -> `bash -n scripts/*.sh`
  -> `pytest -q -m "not archive"`.
- `.github/workflows/orphan_scripts.yml` — the shared orphan-scripts gate.

## Commit Convention

[Conventional Commits](https://www.conventionalcommits.org/):
`type(scope): description`. Common types: `feat`, `fix`, `chore`, `ci`, `docs`,
`refactor`, `test`, `style`, `build`. Use `type!:` or a `BREAKING CHANGE:`
footer for breaking changes.

**Never include AI agents or assistants (Claude, Copilot, Cursor, GPT, Gemini,
…) as co-authors.** Omit all `Co-Authored-By` trailers referencing AI tools,
whether the change was generated, refactored, or reviewed with AI assistance —
the human author is the sole attributable contributor. This is hook-enforced.

## Cross-Repo References

- Downstream reshaper: `hoopR-dev/ncaa-mbb-hoops-data`
- WBB twin (same engine, same rules): `wehoop-dev/ncaa-wbb-hoops-raw`
- SDK internals: <https://github.com/sportsdataverse/sportsdataverse-py/blob/main/CLAUDE.md>
