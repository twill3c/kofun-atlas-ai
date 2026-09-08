"""T-020〜T-025: 逆ジオコーディング後の出荷レコード。

期待値の出所: SPEC §3.2(県の出所)と §7 の G-05 / G-11。
件数は定数で書かず、集合の性質と「経路が実際に通った証拠」で書く。
"""

from __future__ import annotations

import copy
import json

import pytest

from kofun_atlas import geocode, ids, records

pytestmark = pytest.mark.validation

FORBIDDEN_SOURCES = ("nara_hgis",)  # SPEC §4 / G-11


@pytest.fixture(scope="module")
def processed(processed_path):
    return json.loads(processed_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def muni_table(project_root):
    return geocode.load_muni_table(project_root / "data" / "raw" / "gsi" / "muni.js")


def test_t020_prefecture_matches_muni_cd(processed, muni_table):
    """G-05: 県・市区町村が `muni_cd` から導いた値と一致する。"""
    bad = []
    for rec in processed:
        code = rec["muni_cd"]
        if code is None:
            assert rec["prefecture"] is None and rec["municipality"] is None
            continue
        entry = geocode.lookup_muni(code, muni_table)
        if entry is None or rec["prefecture"] != entry.pref_name or (
            rec["municipality"] != entry.muni_name
        ):
            bad.append((rec["id"], code, rec["prefecture"], rec["municipality"]))
    assert bad == [], f"muni_cd と食い違うレコード {len(bad)} 件: {bad[:3]}"


def test_t020_geoshape_prefecture_is_not_the_source(processed):
    """G-05: CSV の県名・県コードを出所とするレコードが 0 件。"""
    bad = [
        rec["id"]
        for rec in processed
        if rec["provenance"].get("prefecture", {}).get("source") == "geoshape"
    ]
    assert bad == [], f"県の出所が geoshape のままのレコード {len(bad)} 件"


def test_t021_positive_control_geocoding_actually_changed_something(
    processed, muni_table
):
    """G-05 の陽性対照: `muniCd` 由来の県と CSV の県コードが食い違う件が実在する。

    0 件なら逆ジオコーディングは何も変えておらず、この経路は検査になっていない
    (HC-071: 新しい要素が狙った状況を実際に一度でも作れているか)。
    """
    disagreements = 0
    for rec in processed:
        code = rec["muni_cd"]
        if code is None:
            continue
        entry = geocode.lookup_muni(code, muni_table)
        assert entry is not None
        if int(entry.pref_code) != int(rec["raw_extra"]["geoshape_pref_code"]):
            disagreements += 1
    assert disagreements > 0, (
        "CSV の県コードと逆ジオコーダが 1 件も食い違わない。"
        "SPEC §3.2 の根拠が失われたか、逆ジオコーディングが効いていない"
    )


def test_t022_final_ids_are_unique_and_recomputable(processed):
    """G-04: 確定 ID が県・市区町村込みで再計算して一致し、重複が無い。"""
    seen = [r["id"] for r in processed]
    assert len(set(seen)) == len(seen)
    for rec in processed:
        assert rec["id"] == ids.kofun_id(
            name=rec["name"],
            prefecture=rec["prefecture"],
            municipality=rec["municipality"],
            lat=rec["location"]["lat"],
            lon=rec["location"]["lon"],
        )


def test_t023_provenance_points_at_the_right_sources(processed):
    """F-06: 値と出所の対応が入れ替わっていない。"""
    for rec in processed:
        assert rec["provenance"]["location"]["source"] == "geoshape"
        assert rec["provenance"]["name"]["source"] == "geoshape"
        if rec["muni_cd"] is not None:
            assert rec["provenance"]["prefecture"]["source"] == "gsi_revgeo"
            assert rec["provenance"]["municipality"]["source"] == "gsi_revgeo"


def test_t024_no_forbidden_source_in_shipped_records(processed):
    """G-11: 禁止ソース由来のデータが出荷物に 0 件。"""
    bad = [
        rec["id"]
        for rec in processed
        if records.uses_forbidden_source(rec, FORBIDDEN_SOURCES)
    ]
    assert bad == [], f"禁止ソースが混入したレコード {len(bad)} 件: {bad[:3]}"


def test_t024_positive_control_forbidden_source_is_detected(processed):
    """G-11 の陽性対照: 混入させた合成レコードを検査が落とす。"""
    assert processed, "走査対象が空でないこと"
    tainted = copy.deepcopy(processed[0])
    tainted["sources"].append(
        {
            "source": "nara_hgis",
            "url": "https://zenkoku-kofun.nara-hgis.jp/",
            "license": "学術研究限定・再配布禁止",
            "retrieved_at": "2026-09-08",
        }
    )
    assert records.uses_forbidden_source(tainted, FORBIDDEN_SOURCES)
    assert not records.uses_forbidden_source(processed[0], FORBIDDEN_SOURCES)


def test_t024_positive_control_detects_forbidden_provenance(processed):
    """出所側に紛れた場合も落ちる(sources だけ見ていると素通りする)。"""
    tainted = copy.deepcopy(processed[0])
    tainted["provenance"]["mound.length_m"] = {
        "source": "nara_hgis",
        "retrieved_at": "2026-09-08",
    }
    assert records.uses_forbidden_source(tainted, FORBIDDEN_SOURCES)


def test_t025_unresolved_points_are_kept_not_dropped(processed, project_root):
    """T-025: 陸上でなかった点は捨てず、件数を manifest に出す。"""
    manifest = json.loads(
        (project_root / "public" / "data" / "data-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    unresolved = [r for r in processed if r["muni_cd"] is None]
    assert manifest["counts"]["without_muni_cd"] == len(unresolved)
    assert manifest["counts"]["records"] == len(processed)
    for rec in unresolved:
        assert rec["quality"]["review_status"] == "manual_review"


# 都道府県の並び(JIS X 0401 の順)。逆ジオコーダの入力ではないので、
# これで CSV の県名を数値化しても循環しない。
PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]
_PREF_NUMBER = {name: i + 1 for i, name in enumerate(PREFECTURES)}


def _csv_fields(rec):
    """CSV が持っていた二つの県欄を番号で返す。"""
    code = int(rec["raw_extra"]["geoshape_pref_code"])
    address_head = rec["raw_extra"]["geoshape_address"].split()[0]
    return code, _PREF_NUMBER.get(address_head)


def test_t028_geocoder_agrees_with_at_least_one_csv_field(processed):
    """T-028: 逆ジオコーダの県が CSV の二欄の少なくとも一方と一致する。

    CSV の県欄は逆ジオコーダに渡していない(渡すのは座標だけ)ので循環しない。
    逆ジオコーダが体系的に狂えば、ここが真っ先に崩れる。
    実測 2026-09-08: 出荷レコード 2,805 件で、両方と食い違うものは 0 件。
    """
    rogue = []
    for rec in processed:
        if rec["muni_cd"] is None:
            continue
        truth = int(rec["muni_cd"][:2])
        code, address = _csv_fields(rec)
        if truth != code and truth != address:
            rogue.append(
                (rec["id"], rec["name"], truth, code, address)
            )
    assert rogue == [], (
        f"CSV のどちらの県欄とも食い違うレコードが {len(rogue)} 件: {rogue[:3]}"
    )


def test_t029_both_csv_fields_are_wrong_somewhere(processed):
    """T-029: 「県コードだけ」「住所だけ」を採る実装に戻したら落ちる。

    実測 2026-09-08(母集団 2,805 件): 県コードが誤 1,569 件 / 住所の県名が誤 1 件。
    どちらも 0 でないことが、SPEC §3.2 の「両方とも単独では信頼できない」の根拠である。
    件数そのものは固定しない —— データが動けば数は動く。
    """
    code_wrong = 0
    address_wrong = 0
    for rec in processed:
        if rec["muni_cd"] is None:
            continue
        truth = int(rec["muni_cd"][:2])
        code, address = _csv_fields(rec)
        if truth != code:
            code_wrong += 1
        if truth != address:
            address_wrong += 1

    assert code_wrong > 0, (
        "県コードが誤ったレコードが 1 件も無い。SPEC §3.2 の根拠が失われている"
    )
    assert address_wrong > 0, (
        "住所の県名が誤ったレコードが 1 件も無い。"
        "住所だけを採る実装で足りることになり、SPEC §3.2 の根拠が変わる"
    )
