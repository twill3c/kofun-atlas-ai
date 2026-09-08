"""T-018 / T-019: 逆ジオコーダ応答と `muniCd` の名称解決。

期待値の出所:
- T-018: 国土地理院 `https://maps.gsi.go.jp/js/muni.js`(2026-09-08 取得)の実物。
  行の形は `GSI.MUNI_ARRAY["1217"] = '1,北海道,1217,江別市';`。
- T-019: 逆ジオコーダの実応答(2026-09-08 実測)。陸上は
  `{"results":{"muniCd":"01217","lv01Nm":"工栄町"}}`、海上・国外は `{}`。
"""

from __future__ import annotations

import pytest

from kofun_atlas import geocode

pytestmark = pytest.mark.unit


def test_t018_muni_table_is_loaded_and_nonempty(project_root):
    table = geocode.load_muni_table(project_root / "data" / "raw" / "gsi" / "muni.js")
    assert len(table) > 1_000, "市区町村表が小さすぎる。読み取りが失敗している"


def test_t018_lookup_is_insensitive_to_leading_zero(project_root):
    """逆ジオコーダは 5 桁ゼロ詰め、表の鍵はゼロ無し。両方で同じ項目を引ける。"""
    table = geocode.load_muni_table(project_root / "data" / "raw" / "gsi" / "muni.js")
    padded = geocode.lookup_muni("01217", table)
    bare = geocode.lookup_muni("1217", table)
    assert padded is not None
    assert padded == bare
    assert padded.pref_name == "北海道"
    assert padded.muni_name == "江別市"


def test_t018_every_entry_maps_to_a_consistent_prefecture(project_root):
    """表の中で、市区町村コードの上 2 桁と県コードが食い違う項目が無い。"""
    table = geocode.load_muni_table(project_root / "data" / "raw" / "gsi" / "muni.js")
    bad = [
        e
        for e in table.values()
        if int(e.muni_cd[:2]) != int(e.pref_code)
    ]
    assert bad == [], f"県コードと市区町村コードが食い違う項目: {bad[:3]}"


def test_t018_positive_control_unknown_code_is_none(project_root):
    table = geocode.load_muni_table(project_root / "data" / "raw" / "gsi" / "muni.js")
    assert geocode.lookup_muni("99999", table) is None


def test_t019_parses_a_land_response():
    payload = {"results": {"muniCd": "01217", "lv01Nm": "工栄町"}}
    assert geocode.parse_response(payload) == ("01217", "工栄町")


def test_t019_empty_object_means_not_on_land_not_a_failure():
    """`{}` は障害ではなく答えである(HC-221 の 404 と同型)。"""
    assert geocode.parse_response({}) == (None, None)
    assert geocode.parse_response({"results": {}}) == (None, None)


def test_t019_malformed_response_raises():
    """想定外の形は黙って None にせず落ちる(HC-075)。"""
    with pytest.raises(ValueError):
        geocode.parse_response({"results": []})


def test_t019_cache_key_is_stable_and_coordinate_shaped():
    a = geocode.revgeo_key(34.5394, 135.8412)
    b = geocode.revgeo_key(34.53940, 135.84120)
    assert a == b
    assert a != geocode.revgeo_key(34.5395, 135.8412)
