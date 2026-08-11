# ncaa-mbb-hoops-raw Copilot Instructions

## Project Context

Raw-page capture + parse pipeline for `stats.ncaa.org` men's college
basketball. Three stages: **discover** (season -> contest_ids) ->
**capture** (contest -> 3-page HTML bundle) -> **parse** (bundle ->
combined per-game JSON), under `mbb/`.

Pipeline: `stats.ncaa.org -> ncaa-mbb-hoops-raw [HERE] -> ncaa-mbb-hoops-data -> sportsdataverse-data`.

**This repo scrapes; it does not reshape.** Tidy season datasets are
`ncaa-mbb-hoops-data`'s job — never mix the two stages.

## ⚠️ Before any live scrape

**Read [`docs/SCRAPING_NOTES.md`](../docs/SCRAPING_NOTES.md) first.**
stats.ncaa.org is a hostile host: patchright + a residential proxy port
pool, a ~70-minute sticky-session ceiling, and a bm-verify solve flow.
The notes carry the access model, the response-class taxonomy, measured
campaign behavior, and the operational rules. `docs/RESUME.md` carries
campaign resume state.

A ban-suspect response is a **hard stop**, not a retry — wait out the
cooldown before resuming. See `README.md` "Safe-rate rule (capture)".

## Repository Workflow

- Branch from `main`; `main` is the default branch.
- `python/` holds flat `ncaa_*` modules run by path — they are **shims over
  `sportsdataverse.scrape.ncaa`**, the shared NCAA hoops engine. Fix
  transport / fetcher / parser bugs **upstream in sdv-py**, not inline here;
  the WBB twin (`ncaa-wbb-hoops-raw`) shares that engine.
- Every stage is idempotent and resumable — see README.md "Resume story".

## Build & Development Commands

```sh
uv sync --frozen
uv run pytest -q -m "not archive"
uv run ruff check python/ tests/

bash scripts/run_01_schedules.sh --season 2026
bash scripts/run_02_games.sh  --season 2026
bash scripts/run_03_parse.sh
```

Wrapper drivers: `run_98_canary.sh` (proxy pre-flight), `run_mbb_backfill.sh`
(single-season chain), `run_mbb_backfill_range.sh` (multi-season campaign),
`run_reference_backfill.sh` (reference-only), `run_04_rosters.sh`,
`run_05_datasets.sh`, `run_autocommit.sh` (settle-aware incremental commits).

## Code Style

- Follow the parent SDK's Python conventions: `snake_case`, 4-space indent.
- Deps live in `pyproject.toml` + `uv.lock` (no `requirements.txt`);
  `sportsdataverse` is pinned to git `main` via `[tool.uv.sources]` and CI
  installs with `uv sync --frozen`.
- ruff is pinned: `select = ["E4","E7","E9","F","I"]`, `ignore = ["E712"]`
  (polars bool masks are written `pl.col("c") == True` on purpose),
  `line-length = 100`. Don't rely on ruff's defaults — they shift between
  versions and turn a green tree red with no code change.
- Tests live in `tests/` at repo **root** (not under `python/`), with
  fixtures in `tests/fixtures/`. pytest is wired with `testpaths = ["tests"]`
  and `pythonpath = ["python"]`.
- Tests needing the full committed `mbb/` tree carry the **`archive`** marker
  and are deselected in CI, which sparse-checks out code only.
- Every script in `scripts/` must be referenced by a runbook, workflow, or
  another script — the shared `orphan-scripts` gate fails otherwise.

## CI

- `tests.yml` — sparse-checkout, `uv sync --frozen`, `ruff check python/ tests/`,
  `bash -n scripts/*.sh`, `pytest -q -m "not archive"`.
- `orphan_scripts.yml` — the shared `sportsdataverse/.github` orphan-scripts gate.

## Cross-Repo References

- Downstream reshaper: <https://github.com/sportsdataverse/ncaa-mbb-hoops-data>
- WBB twin: <https://github.com/sportsdataverse/ncaa-wbb-hoops-raw>
- SDK internals: <https://github.com/sportsdataverse/sportsdataverse-py/blob/main/CLAUDE.md>

## Conventional Commits

Use: `type(scope): description`. Common types: `feat`, `fix`, `chore`, `ci`, `docs`, `refactor`, `test`. Use `type!:` or a `BREAKING CHANGE:` footer for breaking changes.

**Important: Never include AI agents or assistants (e.g., Claude, Copilot, Cursor, GPT, Gemini) as co-authors on commits.** Omit all `Co-Authored-By` trailers referencing AI tools. This applies whether the change was generated, refactored, or reviewed with AI assistance — the human author is the sole attributable contributor.
