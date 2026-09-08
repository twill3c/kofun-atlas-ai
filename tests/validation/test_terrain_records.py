"""T-036: 地形特徴を載せた出荷レコードの分布。

期待値の出所: 日本の陸上がとりうる範囲(外部の一般的事実)と、
定義から決まる角度の範囲。件数は固定しない。
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.validation

# 日本の陸上の標高。最低は八戸鉱山の -170 m 級の人工地形を除けば海面付近、
# 最高は富士山 3,776 m。DEM の欠測・海面付近の負値に幅を持たせる。
ELEVATION_MIN_M = -50.0
ELEVATION_MAX_M = 3800.0


@pytest.fixture(scope="module")
def processed(processed_path):
    return json.loads(processed_path.read_text(encoding="utf-8"))


def _has_terrain(rec):
    return bool(rec.get("terrain")) and "elevation_m" in rec["terrain"]


def test_t036_every_record_has_terrain(processed):
    missing = [r["id"] for r in processed if not _has_terrain(r)]
    assert missing == [], f"地形特徴の無いレコード {len(missing)} 件: {missing[:3]}"


def test_t036_elevation_is_within_japan(processed):
    bad = [
        (r["id"], r["name"], r["terrain"]["elevation_m"])
        for r in processed
        if r["terrain"]["elevation_m"] is not None
        and not (ELEVATION_MIN_M <= r["terrain"]["elevation_m"] <= ELEVATION_MAX_M)
    ]
    assert bad == [], f"標高が日本の範囲外 {len(bad)} 件: {bad[:3]}"


def test_t036_angles_are_within_definition(processed):
    bad = []
    for rec in processed:
        t = rec["terrain"]
        if t["slope_deg"] is not None and not (0 <= t["slope_deg"] <= 90):
            bad.append((rec["id"], "slope", t["slope_deg"]))
        if t["aspect_deg"] is not None and not (0 <= t["aspect_deg"] < 360):
            bad.append((rec["id"], "aspect", t["aspect_deg"]))
    assert bad == [], f"角度が定義域の外 {len(bad)} 件: {bad[:3]}"


def test_t036_relief_is_monotonic_in_radius(processed):
    """半径が広がれば起伏は減らない(窓が包含関係にあるので定義から従う)。"""
    bad = []
    for rec in processed:
        t = rec["terrain"]
        values = [
            t["local_relief_250m"],
            t["local_relief_500m"],
            t["local_relief_1000m"],
        ]
        if any(v is None for v in values):
            continue
        if not (values[0] <= values[1] <= values[2]):
            bad.append((rec["id"], values))
    assert bad == [], f"半径を広げたのに起伏が減ったレコード {len(bad)} 件: {bad[:3]}"


def test_t036_terrain_provenance_is_recorded(processed):
    bad = [
        r["id"]
        for r in processed
        if r["provenance"].get("terrain", {}).get("source") != "gsi_dem"
    ]
    assert bad == [], f"地形の出所が付いていないレコード {len(bad)} 件"


def test_t036_missing_is_null_never_zero(processed):
    """欠測を 0 で埋めていないこと(構想書 §14.5)。

    欠測画素を含むレコードがあるなら、標高が丸ごと欠けた窓は `null` になっている。
    """
    for rec in processed:
        t = rec["terrain"]
        if t["dem_missing_ratio"] == 1.0:
            assert t["elevation_m"] is None
            assert t["slope_deg"] is None
            assert t["local_relief_1000m"] is None


def test_t036_flat_ground_has_null_aspect_not_zero(processed):
    """傾斜 0 の地点の方位は `null`。0 度(北)として出さない。"""
    bad = [
        (r["id"], r["terrain"]["aspect_deg"])
        for r in processed
        if r["terrain"]["slope_deg"] == 0.0 and r["terrain"]["aspect_deg"] is not None
    ]
    assert bad == [], f"平坦地に方位が入っている {len(bad)} 件: {bad[:3]}"
