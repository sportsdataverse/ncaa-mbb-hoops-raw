"""Offline tests for ncaa_mbb_03_games_parse (raw bundle -> combined parsed JSON). No network."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ncaa_mbb_raw_scrape.ncaa_bundle import read_bundle, write_bundle
from ncaa_mbb_03_games_parse import parse_and_write, parse_bundle, write_parsed

_FIX = Path(__file__).resolve().parent / "fixtures" / "ncaa" / "bigballr" / "html"

CONTEST_IDS = [
    "1613299",
    "5722355",
    "5728709",
    "5732292",
    "5733807",
    "6470186",
    "6479592",
    "6479639",
]

FAMILY_KEYS = {"pbp", "lineups", "player_box", "team_box", "shots", "possessions"}
KNOWN_GOOD_GAME = "5722355"


def _fixture_bundle(contest_id: str) -> dict:
    pbp_html = (_FIX / f"pbp_{contest_id}.html").read_text(encoding="utf-8")
    box_html = (_FIX / f"box_{contest_id}.html").read_text(encoding="utf-8")
    stats_html = (_FIX / f"individual_stats_{contest_id}.html").read_text(encoding="utf-8")
    return {
        "contest_id": contest_id,
        "league": "mbb",
        "season": "2024-25",
        "captured_at": "2024-11-14T00:00:00+00:00",
        "urls": {},
        "pages": {
            "play_by_play": pbp_html,
            "box_score": box_html,
            "individual_stats": stats_html,
        },
    }


def test_all_fixtures_produce_six_family_keys() -> None:
    for contest_id in CONTEST_IDS:
        bundle = _fixture_bundle(contest_id)
        parsed = parse_bundle(bundle)
        assert parsed["contest_id"] == contest_id
        assert isinstance(parsed["contest_id"], str)
        assert set(parsed.keys()) == {"contest_id", "teams", *FAMILY_KEYS}
        for key in FAMILY_KEYS:
            assert isinstance(parsed[key], list), f"{contest_id}/{key} not a list"


def test_known_good_game_has_populated_families() -> None:
    bundle = _fixture_bundle(KNOWN_GOOD_GAME)
    parsed = parse_bundle(bundle)
    for key in ("pbp", "lineups", "player_box", "shots", "possessions"):
        assert len(parsed[key]) > 0, f"{KNOWN_GOOD_GAME}/{key} unexpectedly empty"


def test_write_parsed_round_trips_valid_json() -> None:
    bundle = _fixture_bundle(KNOWN_GOOD_GAME)
    parsed = parse_bundle(bundle)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = write_parsed(root, "mbb", KNOWN_GOOD_GAME, parsed)
        assert path == root / "mbb" / "json" / f"{KNOWN_GOOD_GAME}.json"
        assert path.exists()
        # plain utf-8 JSON, not gzip
        reloaded = json.loads(path.read_text(encoding="utf-8"))
        assert reloaded["contest_id"] == KNOWN_GOOD_GAME
        assert set(reloaded.keys()) == {"contest_id", "teams", *FAMILY_KEYS}


def test_parse_and_write_convenience() -> None:
    bundle = _fixture_bundle(KNOWN_GOOD_GAME)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = parse_and_write(bundle, root)
        assert path.exists()
        reloaded = json.loads(path.read_text(encoding="utf-8"))
        assert reloaded["contest_id"] == KNOWN_GOOD_GAME


def test_bundle_written_then_read_still_parses() -> None:
    """Exercise the real write_bundle/read_bundle round trip, not just an in-memory dict."""
    raw = _fixture_bundle(KNOWN_GOOD_GAME)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_bundle(
            root,
            "mbb",
            raw["season"],
            raw["contest_id"],
            pages=raw["pages"],
            urls=raw["urls"],
            captured_at=raw["captured_at"],
        )
        from ncaa_mbb_raw_scrape.ncaa_bundle import bundle_path

        bundle = read_bundle(bundle_path(root, "mbb", raw["season"], raw["contest_id"]))
        parsed = parse_bundle(bundle)
        assert len(parsed["pbp"]) > 0


def test_corrupt_pbp_page_yields_empty_pbp_without_raising() -> None:
    bundle = _fixture_bundle(KNOWN_GOOD_GAME)
    bundle["pages"]["play_by_play"] = ""  # deliberately corrupt
    parsed = parse_bundle(bundle)  # must not raise
    assert parsed["pbp"] == []
    # every downstream family that depends on pbp is also empty, but the call
    # still returns cleanly with all 6 keys present as lists.
    for key in FAMILY_KEYS:
        assert isinstance(parsed[key], list)


def test_every_family_row_carries_contest_id_and_no_game_id() -> None:
    """One per-game identifier, named `contest_id`, on every row of every family."""
    for contest_id in CONTEST_IDS:
        parsed = parse_bundle(_fixture_bundle(contest_id))
        for family in FAMILY_KEYS:
            for row in parsed[family]:
                assert "game_id" not in row, f"{contest_id}/{family} still has game_id"
                assert row["contest_id"] == contest_id, f"{contest_id}/{family} mismatch"
                assert isinstance(row["contest_id"], str), f"{contest_id}/{family} not Utf8"


def test_shots_contest_id_is_populated_and_agrees_with_the_other_families() -> None:
    """Regression: the shots adapter hardcodes `game_id=None`, so shots used to be
    the one family you could not join to the rest without enrichment."""
    parsed = parse_bundle(_fixture_bundle(KNOWN_GOOD_GAME))
    assert len(parsed["shots"]) > 0
    shot_ids = {r["contest_id"] for r in parsed["shots"]}
    pbp_ids = {r["contest_id"] for r in parsed["pbp"]}
    assert shot_ids == pbp_ids == {KNOWN_GOOD_GAME}
    assert None not in shot_ids


def test_contest_id_is_never_a_float_stringification() -> None:
    """`"5722355.0"` is the classic join-breaking defect; the value is the bundle's own str."""
    parsed = parse_bundle(_fixture_bundle(KNOWN_GOOD_GAME))
    for family in FAMILY_KEYS:
        for row in parsed[family]:
            assert "." not in row["contest_id"]


def test_espn_game_id_present_on_every_family_even_without_a_crosswalk() -> None:
    """The column never varies game-to-game: unbuilt crosswalk means null, not absent."""
    parsed = parse_bundle(_fixture_bundle(KNOWN_GOOD_GAME))
    for family in FAMILY_KEYS:
        for row in parsed[family]:
            assert "espn_game_id" in row, f"{family} is missing the espn_game_id column"


def main() -> None:
    test_all_fixtures_produce_six_family_keys()
    test_known_good_game_has_populated_families()
    test_write_parsed_round_trips_valid_json()
    test_parse_and_write_convenience()
    test_bundle_written_then_read_still_parses()
    test_corrupt_pbp_page_yields_empty_pbp_without_raising()
    test_every_family_row_carries_contest_id_and_no_game_id()
    test_shots_contest_id_is_populated_and_agrees_with_the_other_families()
    test_contest_id_is_never_a_float_stringification()
    test_espn_game_id_present_on_every_family_even_without_a_crosswalk()
    print("OK")


if __name__ == "__main__":
    main()
