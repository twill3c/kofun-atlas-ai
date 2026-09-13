"""地図ページが読む資産を作る(SPEC §3.12)。

    python scripts/build_map_assets.py

出力:
  public/data/kofun-points.geojson       一覧・検索・地図に要る最小の欄だけ
  public/data/kofun-details/<xx>.json    詳細。ID の先頭 2 文字(xx)で分割
  tests/fixtures/similar-top10.json      類似検索の照合表(G-26 / T-056)

照合表は `kofun_atlas.features` を**使わずに**、配った埋め込みの内積から独立に作る。
並べる規則は SPEC §3.12 に宣言したとおり:
類似度の降順、同点ならレコードの並び順の昇順、自分自身は除く。
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "kofun.json"
EMBEDDINGS = ROOT / "public" / "data" / "embeddings.json"
POINTS = ROOT / "public" / "data" / "kofun-points.geojson"
DETAILS = ROOT / "public" / "data" / "kofun-details"
FIXTURE = ROOT / "tests" / "fixtures" / "similar-top10.json"

TOP_K = 10
ID_PREFIX = "kofun_"

# 詳細パネルに出す欄。出所を書けない欄は載せない。
TERRAIN_KEYS = (
    "elevation_m",
    "slope_deg",
    "aspect_deg",
    "local_relief_250m",
    "local_relief_500m",
    "local_relief_1000m",
    "relative_elevation_500m",
    "tri",
    "openness_500m",
    "dem_missing_ratio",
)


def shard_of(record_id: str) -> str:
    """ID の先頭 2 文字。`kofun_` を剥がした残りから取る。"""
    if not record_id.startswith(ID_PREFIX):
        raise ValueError(f"ID の形が想定と違う: {record_id}")
    key = record_id[len(ID_PREFIX) : len(ID_PREFIX) + 2]
    if len(key) != 2:
        raise ValueError(f"ID が短すぎて分割できない: {record_id}")
    return key


def top_k_reference(vectors: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """内積の上位 k 件。降順、同点は並び順の昇順、自分自身を除く。

    `np.lexsort` は最後の鍵を第一鍵にして**安定に**並べるので、
    (並び順, -類似度) を渡すと「類似度の降順 → 並び順の昇順」になる。
    """
    n = vectors.shape[0]
    sims = vectors @ vectors.T
    order_idx = np.arange(n)
    ids = np.empty((n, k), dtype=np.int64)
    scores = np.empty((n, k), dtype=np.float64)
    for i in range(n):
        row = sims[i].copy()
        candidates = order_idx[order_idx != i]
        ranked = candidates[np.lexsort((candidates, -row[candidates]))]
        ids[i] = ranked[:k]
        scores[i] = row[ranked[:k]]
    return ids, scores


def main() -> int:
    for path in (PROCESSED, EMBEDDINGS):
        if not path.exists():
            print(f"{path} が無い", file=sys.stderr)
            return 1

    records = json.loads(PROCESSED.read_text(encoding="utf-8"))
    payload = json.loads(EMBEDDINGS.read_text(encoding="utf-8"))
    if payload["ids"] != [r["id"] for r in records]:
        raise ValueError("埋め込みの並びがレコードと違う")

    # --- 地図・一覧用の GeoJSON ---------------------------------------------
    features = []
    for rec in records:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        round(rec["location"]["lon"], 6),
                        round(rec["location"]["lat"], 6),
                    ],
                },
                "properties": {
                    "id": rec["id"],
                    "name": rec["name"],
                    "kana": rec["name_kana"],
                    "pref": rec["prefecture"],
                    "muni": rec["municipality"],
                },
            }
        )
    POINTS.parent.mkdir(parents=True, exist_ok=True)
    POINTS.write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": features},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    # --- 詳細の分割 -----------------------------------------------------------
    shards: dict[str, dict[str, dict]] = {}
    for rec in records:
        detail = {
            "id": rec["id"],
            "name": rec["name"],
            "name_kana": rec["name_kana"],
            "prefecture": rec["prefecture"],
            "municipality": rec["municipality"],
            "lat": rec["location"]["lat"],
            "lon": rec["location"]["lon"],
            "is_group_name": "群" in rec["name"],
            "terrain": {k: (rec.get("terrain") or {}).get(k) for k in TERRAIN_KEYS},
            "external_ids": rec["external_ids"],
            "sources": [
                {k: s.get(k) for k in ("source", "credit", "license", "retrieved_at", "url")}
                for s in rec["sources"]
            ],
        }
        shards.setdefault(shard_of(rec["id"]), {})[rec["id"]] = detail

    DETAILS.mkdir(parents=True, exist_ok=True)
    for stale in DETAILS.glob("*.json"):
        stale.unlink()
    for key, members in sorted(shards.items()):
        (DETAILS / f"{key}.json").write_text(
            json.dumps(members, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

    # --- 類似検索の照合表(独立実装) ----------------------------------------
    vectors = np.asarray(payload["embeddings"], dtype=np.float64)
    ids, scores = top_k_reference(vectors, TOP_K)
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(
        json.dumps(
            {
                "note": (
                    "scripts/build_map_assets.py が public/data/embeddings.json の内積から"
                    "独立に作る。並べる規則: 類似度の降順、同点は並び順の昇順、自分自身を除く"
                    "(SPEC §3.12)。"
                ),
                "top_k": TOP_K,
                "ids": payload["ids"],
                "neighbours": ids.tolist(),
                "scores": [[float(v) for v in row] for row in scores],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    ties = int(sum(1 for row in scores for a, b in zip(row, row[1:]) if a == b))
    print(f"GeoJSON {len(features):,} 件 → {POINTS.stat().st_size:,} バイト")
    print(
        f"詳細 {len(shards)} 分割 / 最大 {max(len(v) for v in shards.values())} 件 / "
        f"最小 {min(len(v) for v in shards.values())} 件"
    )
    print(f"照合表 {len(ids):,} 件 × 上位 {TOP_K} / 上位 10 件の中の隣り合う同点 {ties} 組")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
