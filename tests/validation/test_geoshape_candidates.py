"""T-001〜T-003 / T-006: Geoshape からの候補抽出。

期待値の出所: SPEC §2「母集団と採録範囲(実測 2026-09-08)」。
件数そのものは定数で書かず、SPEC が保証する下限(>= 2,000)と、
集合の性質(取りこぼし・混入の不在)で書く。
"""

from __future__ import annotations

import csv

import pytest

from kofun_atlas import geoshape

pytestmark = pytest.mark.validation

MIN_RECORDS = 2_000  # SPEC §7 G-01 / 構想書 §57
EXCLUDED_CATEGORIES = ("貝塚", "天皇陵", "横穴群")  # SPEC §2


@pytest.fixture(scope="module")
def raw_rows(geoshape_csv):
    with geoshape_csv.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def candidates(geoshape_csv):
    return geoshape.load_candidates(geoshape_csv)


def test_t001_candidate_count_meets_gate(candidates):
    """T-001 / G-01: 候補件数が公開条件の下限を満たす。"""
    assert len(candidates) >= MIN_RECORDS


def test_t001_candidates_are_exactly_the_kofun_category(raw_rows, candidates):
    """T-001: 選ばれた集合が `分類3 == 古墳` の行と過不足なく一致する。"""
    expected = {r["id"] for r in raw_rows if r["分類3"] == "古墳"}
    assert expected, "走査対象が空でないこと(検査そのものが働いている確認)"
    assert {c.source_id for c in candidates} == expected


def test_t002_name_rule_would_lose_records_and_gain_none(raw_rows):
    """T-002: SPEC §3.1「名称正規表現を採用しない」の根拠をデータに固定する。

    この検査はデータに対する不変量であって実装のテストではない。
    Geoshape の版が上がってこの性質が崩れたら、SPEC §3.1 を測り直す合図になる。
    """
    gained = [r for r in raw_rows if r["分類3"] != "古墳" and "古墳" in r["名称"]]
    lost = [r for r in raw_rows if r["分類3"] == "古墳" and "古墳" not in r["名称"]]

    assert gained == [], (
        f"名称規則で拾える非古墳分類の行が {len(gained)} 件ある。SPEC §3.1 を測り直すこと"
    )
    assert lost, "名称規則で取りこぼす行が 1 件も無い。SPEC §3.1 の根拠が失われている"


def test_t003_excluded_categories_are_absent_but_exist(raw_rows, candidates):
    """T-003: 除外分類が候補に混ざらない。かつ CSV に実在する(空振り検査の防止)。"""
    by_id = {r["id"]: r for r in raw_rows}
    for category in EXCLUDED_CATEGORIES:
        present = [r for r in raw_rows if r["分類3"] == category]
        assert present, f"CSV に分類 {category} が 1 件も無い。検査が空振りしている"
        leaked = [c for c in candidates if by_id[c.source_id]["分類3"] == category]
        assert leaked == [], f"分類 {category} が候補に {len(leaked)} 件混入している"


def test_t006_coordinates_are_inside_japan(candidates):
    """T-006 / G-02: 全候補の座標が日本の範囲に入る。"""
    outliers = [
        c for c in candidates if not (20 <= c.lat <= 50 and 120 <= c.lon <= 155)
    ]
    assert outliers == [], f"範囲外座標 {len(outliers)} 件: {outliers[:3]}"


def test_t006_positive_control_out_of_range_is_rejected():
    """T-006 の陽性対照: 範囲外の合成行は落ちる。"""
    bad = geoshape.Candidate(
        source_id="x", name="偽古墳", kana="にせこふん", address="架空県 架空市 架空町",
        pref_code="99", lat=0.0, lon=0.0,
    )
    assert not geoshape.is_inside_japan(bad)
    good = geoshape.Candidate(
        source_id="y", name="箸墓古墳", kana="はしはかこふん", address="奈良県 桜井市 箸中",
        pref_code="29", lat=34.5394, lon=135.8412,
    )
    assert geoshape.is_inside_japan(good)


def test_t006_negative_control_real_rows_are_not_flagged(candidates):
    """T-006 の陰性対照: 実データの正常な部分で誤検出 0(HC-074)。"""
    assert all(geoshape.is_inside_japan(c) for c in candidates)


def test_t001_source_ids_are_unique(candidates):
    """候補の元 ID が一意(Geoshape の id は全 32,038 行で一意 — SPEC §2)。"""
    seen = [c.source_id for c in candidates]
    assert len(set(seen)) == len(seen)
