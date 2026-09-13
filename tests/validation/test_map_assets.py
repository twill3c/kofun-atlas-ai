"""T-058: 地図ページが読む資産。

期待値の出所: SPEC §3.12 と §7 G-02。件数は定数で書かず、
「レコード集合と一致する」「取りこぼし・重複が無い」という不変量で書く。
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.validation

LAT_RANGE = (20.0, 50.0)  # SPEC §7 G-02
LON_RANGE = (120.0, 155.0)


@pytest.fixture(scope="module")
def records(processed_path):
    return json.loads(processed_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def points(project_root, require_artifact):
    path = require_artifact(
        project_root / "public" / "data" / "kofun-points.geojson",
        "`python scripts/build_map_assets.py` を先に実行すること",
    )
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def details_dir(project_root, require_artifact):
    return require_artifact(
        project_root / "public" / "data" / "kofun-details",
        "`python scripts/build_map_assets.py` を先に実行すること",
    )


def test_t058_points_match_the_record_set(points, records):
    got = [f["properties"]["id"] for f in points["features"]]
    assert len(got) == len(set(got)), "GeoJSON に同じ ID が二度ある"
    assert set(got) == {r["id"] for r in records}, "GeoJSON とレコードの集合が違う"


def test_t058_points_are_inside_japan(points):
    bad = [
        f["properties"]["id"]
        for f in points["features"]
        if not (LON_RANGE[0] <= f["geometry"]["coordinates"][0] <= LON_RANGE[1])
        or not (LAT_RANGE[0] <= f["geometry"]["coordinates"][1] <= LAT_RANGE[1])
    ]
    assert bad == [], f"範囲外の点 {len(bad)} 件: {bad[:3]}"


def test_t058_coordinates_are_lon_lat_not_lat_lon(points, records):
    """GeoJSON は [経度, 緯度] の順。取り違えると範囲検査を素通りしうる。"""
    by_id = {r["id"]: r for r in records}
    for f in points["features"][:200]:
        lon, lat = f["geometry"]["coordinates"]
        rec = by_id[f["properties"]["id"]]
        assert lon == pytest.approx(rec["location"]["lon"], abs=1e-6)
        assert lat == pytest.approx(rec["location"]["lat"], abs=1e-6)


def test_t058_detail_shards_cover_every_record_exactly_once(details_dir, records):
    seen: dict[str, str] = {}
    shard_files = sorted(details_dir.glob("*.json"))
    assert shard_files, "詳細の分割ファイルが 1 つも無い"
    for shard in shard_files:
        members = json.loads(shard.read_text(encoding="utf-8"))
        for record_id in members:
            assert record_id not in seen, f"{record_id} が {seen.get(record_id)} と {shard.name} の二つにある"
            seen[record_id] = shard.name
            # 分割の鍵が ID の先頭 2 文字と一致すること(画面はこの規則で引く)
            assert shard.stem == record_id[len("kofun_") : len("kofun_") + 2]
    assert set(seen) == {r["id"] for r in records}, "詳細に取りこぼしがある"


def test_t058_details_carry_sources_and_licence(details_dir):
    for shard in sorted(details_dir.glob("*.json"))[:16]:
        for detail in json.loads(shard.read_text(encoding="utf-8")).values():
            assert detail["sources"], f"{detail['id']} に出典が無い"
            assert all((s.get("license") or "").strip() for s in detail["sources"])
