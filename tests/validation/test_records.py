"""T-007 / T-008: 正規化済みレコードのスキーマ適合と出典。

期待値の出所: `schemas/kofun.schema.json`(構想書 §8 を SPEC §8 で運用化したもの)。
"""

from __future__ import annotations

import copy
import json

import pytest

from kofun_atlas import geoshape, records, schema

pytestmark = pytest.mark.validation


@pytest.fixture(scope="module")
def normalized(geoshape_csv):
    return records.normalize_all(geoshape.load_candidates(geoshape_csv))


@pytest.fixture(scope="module")
def validator(project_root):
    return schema.kofun_validator(project_root / "schemas" / "kofun.schema.json")


def test_t007_all_records_match_schema(normalized, validator):
    """T-007: 全レコードが JSON Schema に適合する。"""
    errors = []
    for rec in normalized:
        for err in validator.iter_errors(rec):
            errors.append((rec["id"], list(err.path), err.message))
            break
    assert errors == [], f"スキーマ違反 {len(errors)} 件: {errors[:3]}"


def test_t007_positive_control_missing_required_field_is_rejected(normalized, validator):
    """T-007 の陽性対照: 必須欄を欠いたレコードは落ちる。"""
    assert normalized, "走査対象が空でないこと"
    broken = copy.deepcopy(normalized[0])
    del broken["location"]
    assert list(validator.iter_errors(broken)), "必須欄を欠いても通ってしまう"


def test_t007_positive_control_out_of_range_latitude_is_rejected(normalized, validator):
    """T-007 の陽性対照: 緯度が範囲外なら落ちる。"""
    broken = copy.deepcopy(normalized[0])
    broken["location"]["lat"] = 0.0
    assert list(validator.iter_errors(broken))


def test_t008_every_record_has_a_licensed_source(normalized):
    """T-008 / G-03: 全レコードが出典を 1 件以上持ち license が空でない。"""
    bad = [
        r["id"]
        for r in normalized
        if not r.get("sources")
        or any(not (s.get("license") or "").strip() for s in r["sources"])
    ]
    assert bad == [], f"出典・license の欠けたレコード {len(bad)} 件: {bad[:3]}"


def test_t008_positive_control_blank_license_is_detected(normalized):
    """T-008 の陽性対照: license を空にしたレコードを検査が捕まえる。"""
    broken = copy.deepcopy(normalized[0])
    broken["sources"][0]["license"] = "   "
    assert not records.has_licensed_source(broken)
    assert records.has_licensed_source(normalized[0])


def test_t008_source_tier_is_publishable(normalized):
    """出荷データに入ってよいのは tier A〜D のみ(SPEC §4 / 構想書 §3)。"""
    tiers = {r["quality"]["source_tier"] for r in normalized}
    assert tiers <= set("ABCD"), f"再配布できない tier が混ざっている: {tiers}"


def test_t007_records_are_json_serialisable(normalized):
    """出荷は JSON なので、そのまま直列化できること。"""
    json.dumps(normalized[:50], ensure_ascii=False)
