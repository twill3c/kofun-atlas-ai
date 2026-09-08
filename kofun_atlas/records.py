"""候補から `KofunRecord` を組み立てる(SPEC §8 / 構想書 §7.1)。

L0 で埋まるのは「位置・名称・読み・出典」だけである。
埋まらない欄は推測で埋めず ``null`` のまま残す —— 古墳研究では
情報が欠けていること自体が情報だから(構想書 §82)。

`prefecture` / `municipality` は **L1 の逆ジオコーディングで確定する**(SPEC §3.2)。
L0 の出力は暫定であり、`data/interim/` に置いて出荷しない。
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Iterable

from . import geoshape, ids

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
GEOSHAPE_MANIFEST = PROJECT_ROOT / "data" / "raw" / "geoshape" / "manifest.json"

# 構想書 §3 のデータ採用レベル。Geoshape は「再利用条件が明確な学術オープンデータ」。
GEOSHAPE_TIER = "B"

# L0 で確定できる欄の数(completeness の分母ではなく、進捗の目安として持つ)。
_REQUIRED_FIELDS = (
    "name",
    "prefecture",
    "municipality",
    "location.lat",
    "location.lon",
    "chronology.year_min",
    "mound.type",
    "mound.length_m",
)


def geoshape_retrieved_at(manifest_path: pathlib.Path | None = None) -> str:
    """Geoshape スナップショットの取得日を manifest から読む。

    取得日を定数で埋め込まない。manifest が無ければ落ちる —— 出典に
    「いつ取ったか」を書けないデータを出荷しないため。
    """
    path = manifest_path or GEOSHAPE_MANIFEST
    if not path.exists():
        raise FileNotFoundError(
            f"{path} が無い。`python scripts/fetch_geoshape.py` を先に実行すること"
        )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    retrieved = manifest.get("retrieved_at")
    if not retrieved:
        raise ValueError(f"{path} に retrieved_at が無い")
    return retrieved


def has_licensed_source(record: dict[str, Any]) -> bool:
    sources = record.get("sources") or []
    return bool(sources) and all(
        (s.get("license") or "").strip() for s in sources
    )


def completeness(record: dict[str, Any]) -> float:
    """埋まっている必須欄の割合(構想書 §31)。重み付けは V1.1 で入れる。"""
    filled = 0
    for path in _REQUIRED_FIELDS:
        node: Any = record
        for key in path.split("."):
            node = (node or {}).get(key) if isinstance(node, dict) else None
        if node is not None:
            filled += 1
    return round(filled / len(_REQUIRED_FIELDS), 4)


def normalize(candidate: geoshape.Candidate, *, retrieved_at: str) -> dict[str, Any]:
    """1 件を `KofunRecord` へ。"""
    name = ids.normalize_name(candidate.name)
    # L0 では県・市区町村が未確定なので、ID も暫定である(SPEC §8)。
    record: dict[str, Any] = {
        "id": ids.kofun_id(
            name=name,
            prefecture=None,
            municipality=None,
            lat=candidate.lat,
            lon=candidate.lon,
        ),
        "name": name,
        "name_kana": ids.normalize_name(candidate.kana) or None,
        "aliases": [],
        "prefecture": None,
        "municipality": None,
        "muni_cd": None,
        "location": {
            "lat": candidate.lat,
            "lon": candidate.lon,
            "accuracy": "point",
            "accuracy_m": None,
            "source": geoshape.SOURCE_ID,
        },
        "chronology": {
            "period_label": None,
            "year_min": None,
            "year_max": None,
            "source_kind": "unknown",
            "confidence": None,
        },
        "mound": {
            "type": "unknown",
            "length_m": None,
            "width_m": None,
            "height_m": None,
            "moat": None,
            "fukiishi": None,
            "haniwa": None,
        },
        "burial": {"chamber_type": None, "coffin_type": None},
        "artifacts": {
            "mirror": None,
            "weapon": None,
            "armor": None,
            "horse_gear": None,
            "ornament": None,
        },
        "heritage": {"designation": None, "designation_date": None, "bunka_id": None},
        "terrain": {},
        "ai": {},
        "external_ids": {
            "geoshape": candidate.source_id,
            "wikidata": None,
            "bunka": None,
            "nabunken_jcno": None,
        },
        # SPEC §3.2: 採用しなかった元の県名・県コードは捨てずに退避する。
        "raw_extra": {
            "geoshape_pref_code": candidate.pref_code,
            "geoshape_address": candidate.address,
            "geoshape_municipality_hint": candidate.municipality_hint,
        },
        "provenance": {
            "name": {"source": geoshape.SOURCE_ID, "retrieved_at": retrieved_at},
            "location": {"source": geoshape.SOURCE_ID, "retrieved_at": retrieved_at},
        },
        "quality": {
            "source_tier": GEOSHAPE_TIER,
            "completeness": 0.0,
            "entity_match_confidence": None,
            "review_status": "pending_geocode",
            "flags": ["Q11"],  # 市区町村までしか確定していない(構想書 Appendix C)
        },
        "sources": [
            {
                "source": geoshape.SOURCE_ID,
                "url": geoshape.SOURCE_URL,
                "license": geoshape.SOURCE_LICENSE,
                "credit": geoshape.SOURCE_CREDIT,
                "retrieved_at": retrieved_at,
            }
        ],
    }
    record["quality"]["completeness"] = completeness(record)
    return record


def normalize_all(
    candidates: Iterable[geoshape.Candidate],
    *,
    retrieved_at: str | None = None,
) -> list[dict[str, Any]]:
    stamp = retrieved_at or geoshape_retrieved_at()
    cands = list(candidates)

    # 源の内側にも同じ実体の重複がある(SPEC §3.6 / HC-223)。
    # 同じ内部 ID に落ちた候補は「同名・同じ 4 桁丸め座標」であり、
    # canonical_text の定義からそれ以外の落ち方をしない。統合してよい。
    merged: dict[str, dict[str, Any]] = {}
    for cand in cands:
        record = normalize(cand, retrieved_at=stamp)
        first = merged.get(record["id"])
        if first is None:
            merged[record["id"]] = record
            continue

        # 統合の根拠が本当に成り立っているかを、その場で確かめる(HC-075)。
        if first["name"] != record["name"]:
            raise ValueError(
                f"内部 ID {record['id']} が名称の違う 2 件を束ねた: "
                f"{first['name']!r} と {record['name']!r}"
            )
        first["raw_extra"].setdefault("geoshape_duplicate_ids", []).append(
            cand.source_id
        )

    return list(merged.values())
