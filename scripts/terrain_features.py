"""キャッシュ済み標高タイルから地形特徴量を算出し、派生値だけを書き出す。

    python scripts/terrain_features.py

入力: `data/processed/kofun.json` と `data/raw/gsi-cache/`(ローカルのみ)
出力: `data/derived/terrain.jsonl`(**リポジトリに同梱する**)

全国 DEM そのものは再配布しない(構想書 §2.4)。同梱するのは
「座標 → 地形特徴量」の対応だけで、これがあれば CI もクローンも
一度も国土地理院を叩かずに同じレコードを再現できる。
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from kofun_atlas import geocode, terrain, tiles  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "kofun.json"
CACHE = ROOT / "data" / "raw" / "gsi-cache"
INDEX = CACHE / "index.jsonl"
OUT = ROOT / "data" / "derived" / "terrain.jsonl"
MANIFEST = ROOT / "data" / "derived" / "manifest.json"

RELIEF_RADII_M = (250.0, 500.0, 1000.0)
RELATIVE_RADIUS_M = 500.0
OPENNESS_RADIUS_M = 500.0


def features_for(store: tiles.TileStore, lon: float, lat: float) -> dict:
    grid, mpp, contributions = store.window(lon, lat)
    centre = grid[grid.shape[0] // 2, grid.shape[1] // 2]
    slope, aspect = terrain.slope_aspect(grid, mpp)

    out: dict = {
        "elevation_m": None if centre != centre else round(float(centre), 2),
        "slope_deg": None if slope is None else round(slope, 3),
        "aspect_deg": terrain.round_aspect(aspect),
        "tri": None,
        "relative_elevation_500m": None,
        "openness_500m": None,
        "dem_zoom": tiles.DEFAULT_ZOOM,
        "dem_layers": dict(sorted(contributions.items())),
        "dem_missing_ratio": round(terrain.missing_ratio(grid), 4),
    }
    value = terrain.tri(grid, mpp)
    out["tri"] = None if value is None else round(value, 3)
    value = terrain.relative_elevation(grid, mpp, RELATIVE_RADIUS_M)
    out["relative_elevation_500m"] = None if value is None else round(value, 2)
    value = terrain.openness_proxy(grid, mpp, OPENNESS_RADIUS_M)
    out["openness_500m"] = None if value is None else round(value, 4)
    for radius in RELIEF_RADII_M:
        value = terrain.local_relief(grid, mpp, radius)
        out[f"local_relief_{int(radius)}m"] = None if value is None else round(value, 2)
    return out


def main() -> int:
    for path in (PROCESSED, INDEX):
        if not path.exists():
            print(f"{path} が無い", file=sys.stderr)
            return 1

    records = json.loads(PROCESSED.read_text(encoding="utf-8"))
    store = tiles.TileStore(CACHE, INDEX)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, rec in enumerate(records, 1):
        lon, lat = rec["location"]["lon"], rec["location"]["lat"]
        row = {"key": geocode.revgeo_key(lat, lon)}
        row.update(features_for(store, lon, lat))
        rows.append(row)
        if index % 500 == 0:
            print(f"  {index:,}/{len(records):,}", flush=True)

    with OUT.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    layers: dict[str, int] = {}
    for row in rows:
        for layer, count in row["dem_layers"].items():
            layers[layer] = layers.get(layer, 0) + count
    missing = [r for r in rows if r["dem_missing_ratio"] > 0]

    MANIFEST.write_text(
        json.dumps(
            {
                "source": "gsi_dem",
                "derived_from": "国土地理院 標高タイル",
                "credit": "国土地理院の標高データを加工して作成",
                "license": "国土地理院コンテンツ利用規約",
                "generated_at": dt.date.today().isoformat(),
                "zoom": tiles.DEFAULT_ZOOM,
                "radius_m": tiles.DEFAULT_RADIUS_M,
                "records": len(rows),
                "tile_layers": layers,
                "records_with_missing_pixels": len(missing),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"レコード {len(rows):,} 件 → {OUT}({OUT.stat().st_size:,} バイト)")
    print(f"タイル層の内訳(のべ): {layers}")
    print(f"欠測画素を含むレコード: {len(missing):,} 件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
