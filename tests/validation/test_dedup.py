"""T-016 / T-017: 源の内側の重複統合(SPEC §3.6 / HC-223)。

期待値の出所: 実測(2026-09-08)。母集団は Geoshape `分類3 == 古墳` の 2,808 行で、
同一内部 ID になる組が 3 組 6 行あった —— 富士山古墳(栃木県壬生町)/
狐塚古墳(山梨県笛吹市)/芝古墳群(長岡京市)。
件数は定数で書かず「1 組以上ある」ことだけを固定する。データが動けば数は動くが、
**統合経路が一度も通らないまま緑になる**ことだけは防ぐ。
"""

from __future__ import annotations

import pytest

from kofun_atlas import geoshape, ids, records

pytestmark = pytest.mark.validation


@pytest.fixture(scope="module")
def candidates(geoshape_csv):
    return geoshape.load_candidates(geoshape_csv)


@pytest.fixture(scope="module")
def normalized(candidates):
    return records.normalize_all(candidates)


def test_t016_ids_are_unique_after_merge(normalized):
    """G-04: 統合後の内部 ID は一意。"""
    seen = [r["id"] for r in normalized]
    assert len(set(seen)) == len(seen)


def test_t016_merge_actually_happened(candidates, normalized):
    """統合が実際に起きた証拠を残す(HC-071)。

    起きていなければ、統合の実装は一度も動かないまま緑を返す。
    """
    assert len(normalized) < len(candidates), (
        "統合された組が 1 組も無い。SPEC §3.6 の根拠が失われたか、統合が働いていない"
    )


def test_t016_no_source_row_is_dropped(candidates, normalized):
    """統合しても元の Geoshape id は 1 件も落ちない。"""
    kept = set()
    for rec in normalized:
        kept.add(rec["external_ids"]["geoshape"])
        kept.update(rec["raw_extra"].get("geoshape_duplicate_ids", []))
    assert kept == {c.source_id for c in candidates}


def test_t016_merged_members_agree_on_name_and_rounded_coords(normalized):
    """統合された組は、名称と 4 桁丸め座標が一致している(統合の根拠)。"""
    merged = [r for r in normalized if r["raw_extra"].get("geoshape_duplicate_ids")]
    assert merged, "統合されたレコードが無い"
    for rec in merged:
        recomputed = ids.kofun_id(
            name=rec["name"],
            prefecture=rec["prefecture"],
            municipality=rec["municipality"],
            lat=rec["location"]["lat"],
            lon=rec["location"]["lon"],
        )
        assert recomputed == rec["id"]


def test_t017_positive_control_different_names_are_not_merged():
    """T-017: 名称が違えば同じ座標でも統合しない。"""
    a = geoshape.Candidate("a", "甲古墳", "こう", "県 市 町", "29", 34.5394, 135.8412)
    b = geoshape.Candidate("b", "乙古墳", "おつ", "県 市 町", "29", 34.5394, 135.8412)
    out = records.normalize_all([a, b], retrieved_at="2026-09-08")
    assert len(out) == 2


def test_t017_same_name_and_rounded_coords_are_merged():
    """T-017: 名称一致・4 桁丸めで座標一致なら統合する。"""
    a = geoshape.Candidate("a", "甲古墳", "こう", "県 市 町", "29", 34.53940, 135.84120)
    b = geoshape.Candidate("b", "甲古墳", "こう", "県 市 町", "29", 34.539404, 135.841199)
    out = records.normalize_all([a, b], retrieved_at="2026-09-08")
    assert len(out) == 1
    assert out[0]["raw_extra"]["geoshape_duplicate_ids"] == ["b"]
