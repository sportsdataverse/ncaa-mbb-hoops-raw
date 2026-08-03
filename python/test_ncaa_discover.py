"""Offline tests for season -> contest_id discovery (no network)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import polars as pl
import pytest

from ncaa_discover import _season_str, discover_season

# Sibling checkout: .../sdv-dev/{hoopR-dev/ncaa-mbb-hoops-raw, sdv-py}.
FIXTURE = (
    Path(__file__).resolve().parent
    / "tests"
    / "fixtures"
    / "ncaa"
    / "bigballr"
    / "html"
    / "team_609554.html"
)
_HTML = FIXTURE.read_text(encoding="utf-8")


def test_discover_season_offline() -> None:
    df = discover_season(2020, league="mbb", limit_teams=1, team_ids=[609554], fetch_fn=lambda tid: _HTML)

    assert df.schema["contest_id"] == pl.Utf8
    assert df.height > 0
    contest_ids = df.get_column("contest_id").to_list()
    assert all(isinstance(c, str) and c != "" for c in contest_ids)
    assert len(contest_ids) == len(set(contest_ids))  # no duplicates


def test_discover_season_dedups_across_teams() -> None:
    # Two distinct team_ids fed the SAME fixture page -> same contest_id set
    # on both "schedules" -> dedup must collapse the union back to one copy.
    solo = discover_season(2020, team_ids=[609554], fetch_fn=lambda tid: _HTML)
    two_teams = discover_season(2020, team_ids=[609554, 700000], fetch_fn=lambda tid: _HTML)

    assert two_teams.height == solo.height
    assert set(two_teams.get_column("contest_id").to_list()) == set(solo.get_column("contest_id").to_list())


def test_write_master_merges_and_preserves_captured() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        discover_season(2020, team_ids=[609554], fetch_fn=lambda tid: _HTML, root=root)

        master_path = root / "mbb" / "schedule_master.parquet"
        assert master_path.exists()

        master = pl.read_parquet(master_path)
        assert set(master.columns) == {"contest_id", "season", "captured"}
        assert (master.get_column("captured") == False).all()  # noqa: E712

        # Simulate a downstream capture step flipping one row to True, then
        # re-run discovery -- the captured=True row must survive the merge.
        first_id = master.get_column("contest_id")[0]
        updated = master.with_columns(
            pl.when(pl.col("contest_id") == first_id).then(True).otherwise(pl.col("captured")).alias("captured")
        )
        updated.write_parquet(master_path)

        discover_season(2020, team_ids=[609554], fetch_fn=lambda tid: _HTML, root=root)
        after = pl.read_parquet(master_path)
        row = after.filter(pl.col("contest_id") == first_id)
        assert row.get_column("captured")[0] == True  # noqa: E712
        assert after.height == master.height  # re-run adds nothing new


def test_season_str_conversion() -> None:
    # Ending-year int -> crosswalk "YYYY-YY" format (the live-path filter key).
    assert _season_str(2026) == "2025-26"
    assert _season_str(2010) == "2009-10"


def test_discover_season_present_season_selects_teams_from_real_crosswalk() -> None:
    # 2026 -> "2025-26", a season the bundled crosswalk actually contains --
    # exercises the real (unmocked) crosswalk filter end to end, not team_ids bypass.
    df = discover_season(2026, league="mbb", limit_teams=3, fetch_fn=lambda tid: _HTML)
    assert df.height > 0


def test_discover_season_raises_on_crosswalk_format_drift() -> None:
    # No team plays in a season this far outside the bundled crosswalk range
    # -- must fail loudly, not return an empty, complete-looking frame.
    with pytest.raises(ValueError):
        discover_season(1900, fetch_fn=lambda tid: _HTML)


def main() -> None:
    test_discover_season_offline()
    test_discover_season_dedups_across_teams()
    test_write_master_merges_and_preserves_captured()
    test_season_str_conversion()
    test_discover_season_present_season_selects_teams_from_real_crosswalk()
    test_discover_season_raises_on_crosswalk_format_drift()
    print("OK")


if __name__ == "__main__":
    main()


def test_discover_resumes_from_checkpoint(tmp_path):
    """An aborted sweep's checkpointed teams are NOT refetched on re-run."""
    import ncaa_discover as nd

    def flaky_fetch(team_id):
        if team_id == 2:
            raise RuntimeError("BAN-SUSPECT:stub")
        return _HTML

    # First run: team 2 fails all retries -> skipped (tolerant sweep); teams
    # 1 + 3 succeed and are checkpointed to disk.
    out1 = nd.discover_season(
        2020, team_ids=[1, 2, 3], fetch_fn=flaky_fetch, root=tmp_path
    )
    assert out1.height > 0
    scratch = tmp_path / "mbb" / ".discover" / "2020"
    assert sorted(p.stem for p in scratch.glob("*.json")) == ["1", "3"]

    # Second run: teams 1 + 3 must come from the checkpoint (fetch would now
    # blow up for them); only the previously-skipped team 2 is fetched.
    def second_fetch(team_id):
        assert team_id == 2, f"checkpointed team {team_id} was refetched"
        return _HTML

    out2 = nd.discover_season(
        2020, team_ids=[1, 2, 3], fetch_fn=second_fetch, root=tmp_path
    )
    assert set(out2.get_column("contest_id").to_list()) == set(
        out1.get_column("contest_id").to_list()
    )


def test_discover_shard_slices_and_skips_master(tmp_path):
    """A sharded run sweeps only its slice and never writes schedule_master."""
    import ncaa_discover as nd

    seen: "list[int]" = []

    def fetch(team_id):
        seen.append(team_id)
        return _HTML

    ids = [1, 2, 3, 4, 5, 6]
    nd.discover_season(
        2020, team_ids=ids, fetch_fn=fetch, root=tmp_path, shard=(1, 3),
        write_master=False,
    )
    assert seen == [2, 5]  # ids[1::3]
    assert not (tmp_path / "mbb" / "schedule_master.parquet").exists()

    # Remaining shards, then the merge pass: it re-reads every shard's
    # checkpoints, fetches nothing new, and writes the master.
    for i in (0, 2):
        nd.discover_season(
            2020, team_ids=ids, fetch_fn=fetch, root=tmp_path, shard=(i, 3),
            write_master=False,
        )
    swept = len(seen)
    out = nd.discover_season(2020, team_ids=ids, fetch_fn=fetch, root=tmp_path)
    assert len(seen) == swept  # merge pass fetched nothing
    assert out.height > 0
    assert (tmp_path / "mbb" / "schedule_master.parquet").exists()
