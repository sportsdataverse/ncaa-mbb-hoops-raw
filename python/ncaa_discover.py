"""Season -> contest_id discovery (team-ids -> schedules -> dedup).

Reuses the bigballR port already vendored in sdv-py: the ``(team, season) ->
id`` crosswalk (:func:`ncaa_mbb_team_ids`), the team-schedule-page parser
(:func:`parse_ncaa_bb_team_schedule`), and the browser-transport fetcher
(:class:`NcaaFetcher`) for the live path. Each game appears on two teams'
schedules, so the core job here is: fetch every team page for a season,
extract ``contests/{id}/`` links, and dedup across teams.
"""

from __future__ import annotations

import concurrent.futures as cf
import logging
import os
from pathlib import Path
from typing import Callable, List, Optional, Union

import polars as pl

from sportsdataverse.mbb.mbb_ncaa_schedule import parse_ncaa_bb_team_schedule
from sportsdataverse.mbb.mbb_ncaa_team_ids import ncaa_mbb_team_ids

logger = logging.getLogger(__name__)

FetchFn = Callable[[int], str]

_MASTER_COLUMNS: List[str] = ["contest_id", "season", "captured"]

__all__ = ["discover_season"]


def _default_fetch_fn() -> FetchFn:
    """Live fetch: one shared browser-transport session, ``teams/{id}``."""
    from sportsdataverse.mbb.mbb_ncaa_fetch import NcaaFetcher

    fetcher = NcaaFetcher.with_browser()
    return lambda team_id: fetcher.fetch_html(f"teams/{team_id}")


def _team_contest_ids(team_id: int, fetch_fn: FetchFn, league: str) -> List[str]:
    try:
        html = fetch_fn(team_id)
    except RuntimeError:
        # NcaaFetcher raises RuntimeError on a ban-suspect / exhausted-proxy
        # response ("BAN-SUSPECT:<marker>" is folded into the message) --
        # hard stop rather than silently skipping the team.
        logger.error("NCAA discovery hard-stopped on team_id=%s (ban-suspect / fetch failure)", team_id)
        raise
    schedule = parse_ncaa_bb_team_schedule(html, team_id, league=league)
    return schedule.get_column("game_id").drop_nulls().to_list()


def discover_season(
    season: Union[int, str],
    *,
    league: str = "mbb",
    workers: int = 1,
    limit_teams: Optional[int] = None,
    fetch_fn: Optional[FetchFn] = None,
    team_ids: Optional[List[int]] = None,
    root: Optional[Union[str, Path]] = None,
) -> pl.DataFrame:
    """Discover every ``contest_id`` played in *season* by sweeping team pages.

    Args:
        season: Season to discover. Used both to filter the bundled
            ``(team, season) -> id`` crosswalk (live path) and to stamp the
            returned frame's ``season`` column.
        league: ``"mbb"`` or ``"wbb"`` (only ``mbb``'s crosswalk is bundled
            as of this task; passed through to the schedule parser).
        workers: Thread-pool fan-out for team-page fetches. Overridden by the
            ``NCAA_WORKERS`` env var when set.
        limit_teams: Cap the number of teams swept (a small live smoke, e.g.
            one conference).
        fetch_fn: ``team_id -> html``. Defaults to a live fetch through one
            shared :class:`NcaaFetcher.with_browser` session (the team page
            can be Akamai-challenged like game pages). Inject a fake for
            offline tests.
        team_ids: Explicit team id list that bypasses the crosswalk filter
            entirely -- lets offline tests drive discovery without the
            crosswalk having the fixture's team id for the given season.
        root: If given, also write/merge ``{root}/{league}/schedule_master.
            parquet`` (columns ``contest_id``, ``season``, ``captured``).

    Returns:
        One row per unique ``contest_id`` (deduped across teams, sorted):
        ``contest_id`` (Utf8), ``season`` (Utf8).

    Raises:
        RuntimeError: A team-page fetch hit a ban-suspect / exhausted-proxy
            response -- discovery stops immediately rather than returning a
            partial result silently.
    """
    if team_ids is not None:
        ids = list(team_ids)
    else:
        crosswalk = ncaa_mbb_team_ids()
        ids = crosswalk.filter(pl.col("season") == str(season)).get_column("id").to_list()
    if limit_teams is not None:
        ids = ids[:limit_teams]

    fn = fetch_fn if fetch_fn is not None else _default_fetch_fn()
    n_workers = int(os.environ.get("NCAA_WORKERS", workers))

    contest_ids: "set[str]" = set()
    if n_workers > 1 and len(ids) > 1:
        with cf.ThreadPoolExecutor(max_workers=n_workers) as ex:
            for team_ids_batch in ex.map(lambda tid: _team_contest_ids(tid, fn, league), ids):
                contest_ids.update(team_ids_batch)
    else:
        for team_id in ids:
            contest_ids.update(_team_contest_ids(team_id, fn, league))

    result = pl.DataFrame({"contest_id": sorted(contest_ids)}, schema={"contest_id": pl.Utf8}).with_columns(
        pl.lit(str(season)).alias("season")
    )

    if root is not None:
        _write_master(result, root, league)

    return result


def _write_master(result: pl.DataFrame, root: Union[str, Path], league: str) -> Path:
    """Merge *result* into ``{root}/{league}/schedule_master.parquet``.

    Add-column-if-absent guard for ``captured`` (schema predates the column
    on an older master file), then union new contest_ids in without
    dropping any existing ``captured=True`` row.
    """
    path = Path(root) / league / "schedule_master.parquet"
    new_rows = result.with_columns(pl.lit(False).alias("captured")).select(_MASTER_COLUMNS)

    if path.exists():
        existing = pl.read_parquet(path)
        if "captured" not in existing.columns:
            existing = existing.with_columns(pl.lit(False).alias("captured"))
        combined = (
            pl.concat([existing.select(_MASTER_COLUMNS), new_rows], how="diagonal_relaxed")
            .sort("captured", descending=True)
            .unique(subset="contest_id", keep="first")
        )
    else:
        combined = new_rows

    combined = combined.select(_MASTER_COLUMNS).sort("contest_id")
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.write_parquet(path)
    return path
