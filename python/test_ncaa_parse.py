"""Offline tests for ncaa_parse (raw bundle -> combined parsed JSON). No network."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ncaa_bundle import read_bundle, write_bundle
from ncaa_parse import parse_and_write, parse_bundle, write_parsed

_SDV_PY_ROOT = Path(__file__).resolve().parents[3] / "sdv-py"
_FIX = _SDV_PY_ROOT / "tests" / "fixtures" / "ncaa" / "bigballr" / "html"

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
        assert set(parsed.keys()) == {"contest_id", *FAMILY_KEYS}
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
        assert set(reloaded.keys()) == {"contest_id", *FAMILY_KEYS}


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
        from ncaa_bundle import bundle_path

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


def main() -> None:
    test_all_fixtures_produce_six_family_keys()
    test_known_good_game_has_populated_families()
    test_write_parsed_round_trips_valid_json()
    test_parse_and_write_convenience()
    test_bundle_written_then_read_still_parses()
    test_corrupt_pbp_page_yields_empty_pbp_without_raising()
    print("OK")


if __name__ == "__main__":
    main()
