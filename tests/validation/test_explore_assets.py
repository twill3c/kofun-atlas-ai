"""T-066: 探索画面が読む資産の並びと値。

期待値の出所: SPEC §3.14。件数は定数で書かず、他の出荷物との一致で書く。
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.validation

METRICS = ("elevation_m", "slope_deg", "openness_500m")


@pytest.fixture(scope="module")
def explore(project_root, require_artifact):
    path = require_artifact(
        project_root / "public" / "data" / "explore.json",
        "`python scripts/build_explore_assets.py` を先に実行すること",
    )
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def records(processed_path):
    return {r["id"]: r for r in json.loads(processed_path.read_text(encoding="utf-8"))}


def test_t066_order_and_coordinates_match_the_projection(explore, project_root):
    projection = json.loads(
        (project_root / "public" / "data" / "projection.json").read_text(encoding="utf-8")
    )
    assert explore["ids"] == projection["ids"]
    assert explore["xy"] == projection["xy"]


def test_t066_names_and_places_match_the_points(explore, project_root):
    points = json.loads(
        (project_root / "public" / "data" / "kofun-points.geojson").read_text(encoding="utf-8")
    )
    feats = points["features"]
    assert explore["ids"] == [f["properties"]["id"] for f in feats]
    assert explore["name"] == [f["properties"]["name"] for f in feats]
    assert explore["pref"] == [f["properties"]["pref"] for f in feats]
    assert explore["lonlat"] == [f["geometry"]["coordinates"] for f in feats]


def test_t066_metric_values_match_the_records(explore, records):
    for m in METRICS:
        column = explore["metrics"][m]
        assert len(column) == len(explore["ids"])
        for record_id, value in zip(explore["ids"], column, strict=True):
            assert value == records[record_id]["terrain"].get(m), (record_id, m)


def test_t066_missing_values_stay_null(explore, records):
    """値なしは null のまま。0 で埋めない。"""
    for m in METRICS:
        expected_nulls = sum(1 for r in records.values() if r["terrain"].get(m) is None)
        assert explore["metrics"][m].count(None) == expected_nulls
