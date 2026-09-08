"""T-026: `apply_geocode` の二分岐を、実データを使わずに通す。

期待値の出所: SPEC §3.2(県の出所)と §8(ID の定義)。
"""

from __future__ import annotations

import pytest

from kofun_atlas import geocode, geoshape, ids, records

pytestmark = pytest.mark.unit

RETRIEVED = "2026-09-08"
ENTRY = geocode.MuniEntry(
    pref_code="29", pref_name="奈良県", muni_cd="29206", muni_name="桜井市"
)


@pytest.fixture
def base_record():
    candidate = geoshape.Candidate(
        source_id="290000000000",
        name="箸墓古墳",
        kana="はしはかこふん",
        address="大阪府 桜井市 箸中",  # わざと誤った県名(SPEC §3.2 の破れを模す)
        pref_code="30",  # わざと誤った県コード
        lat=34.5394,
        lon=135.8412,
    )
    return records.normalize(candidate, retrieved_at=RETRIEVED)


def test_t026_resolved_point_gets_names_provenance_and_new_id(base_record):
    before = base_record["id"]
    out = records.apply_geocode(
        base_record, muni_entry=ENTRY, lv01="大字箸中", retrieved_at=RETRIEVED
    )

    assert out["prefecture"] == "奈良県"
    assert out["municipality"] == "桜井市"
    assert out["muni_cd"] == "29206"
    assert out["raw_extra"]["gsi_lv01Nm"] == "大字箸中"

    # 採用しなかった CSV の値は消さずに残す。
    assert out["raw_extra"]["geoshape_pref_code"] == "30"
    assert "大阪府" in out["raw_extra"]["geoshape_address"]

    for field in ("prefecture", "municipality", "muni_cd"):
        assert out["provenance"][field]["source"] == geocode.SOURCE_ID
    assert out["provenance"]["location"]["source"] == geoshape.SOURCE_ID

    assert out["quality"]["review_status"] == "auto_accepted"
    assert "Q11" not in out["quality"]["flags"]

    assert out["id"] != before, "県・市区町村が入れば ID は振り直される"
    assert out["id"] == ids.kofun_id(
        name=out["name"],
        prefecture="奈良県",
        municipality="桜井市",
        lat=34.5394,
        lon=135.8412,
    )


def test_t026_unresolved_point_is_kept_with_nulls(base_record):
    before = base_record["id"]
    out = records.apply_geocode(
        base_record, muni_entry=None, lv01=None, retrieved_at=RETRIEVED
    )

    assert out["prefecture"] is None
    assert out["municipality"] is None
    assert out["muni_cd"] is None
    assert out["quality"]["review_status"] == "manual_review"
    assert "Q10" in out["quality"]["flags"]
    assert out["id"] == before, "確定していないのに ID を変えない"
    assert "prefecture" not in out["provenance"], (
        "入っていない値に出所を付けない"
    )


def test_t026_placeholder_lv01_is_not_stored(base_record):
    """`lv01Nm` は大字が無いとき全角ハイフンを返す。それを地名として残さない。"""
    out = records.apply_geocode(
        base_record, muni_entry=ENTRY, lv01="−", retrieved_at=RETRIEVED
    )
    assert "gsi_lv01Nm" not in out["raw_extra"]


def test_t026_does_not_mutate_the_input(base_record):
    snapshot = dict(base_record)
    records.apply_geocode(
        base_record, muni_entry=ENTRY, lv01="大字箸中", retrieved_at=RETRIEVED
    )
    assert base_record["prefecture"] is None
    assert base_record["id"] == snapshot["id"]
