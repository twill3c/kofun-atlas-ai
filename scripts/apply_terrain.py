"""同梱の派生地形特徴量を出荷レコードへ載せる。

    python scripts/apply_terrain.py

`data/derived/terrain.jsonl` だけを読むので、標高タイルのキャッシュが無くても走る。
CI とクローンはこの経路を通る。
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from kofun_atlas import geocode, schema  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "kofun.json"
DERIVED = ROOT / "data" / "derived" / "terrain.jsonl"
MANIFEST = ROOT / "data" / "derived" / "manifest.json"

# レコードへ載せる欄。出所を書けない欄は載せない。
FEATURE_KEYS = (
    "elevation_m",
    "slope_deg",
    "aspect_deg",
    "local_relief_250m",
    "local_relief_500m",
    "local_relief_1000m",
    "relative_elevation_500m",
    "tri",
    "openness_500m",
    "dem_zoom",
    "dem_layers",
    "dem_missing_ratio",
)


def main() -> int:
    for path in (PROCESSED, DERIVED, MANIFEST):
        if not path.exists():
            print(f"{path} が無い", file=sys.stderr)
            return 1

    records = json.loads(PROCESSED.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    retrieved_at = manifest["generated_at"]

    derived = {}
    for line in DERIVED.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            derived[row["key"]] = row

    missing = []
    for rec in records:
        key = geocode.revgeo_key(rec["location"]["lat"], rec["location"]["lon"])
        row = derived.get(key)
        if row is None:
            missing.append(rec["id"])
            continue
        rec["terrain"] = {k: row[k] for k in FEATURE_KEYS}
        rec["provenance"]["terrain"] = {
            "source": "gsi_dem",
            "retrieved_at": retrieved_at,
        }

    if missing:
        print(
            f"地形特徴が無いレコードが {len(missing)} 件ある。"
            f"`python scripts/terrain_features.py` を先に走らせること: {missing[:3]}",
            file=sys.stderr,
        )
        return 1

    validator = schema.kofun_validator()
    errors = [
        (rec["id"], err.message)
        for rec in records
        for err in validator.iter_errors(rec)
    ]
    if errors:
        print(f"スキーマ違反 {len(errors)} 件: {errors[:5]}", file=sys.stderr)
        return 1

    PROCESSED.write_text(
        json.dumps(records, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    with_elev = sum(1 for r in records if r["terrain"]["elevation_m"] is not None)
    print(f"レコード {len(records):,} 件に地形特徴を載せた(標高あり {with_elev:,} 件)")
    print(f"書き出し: {PROCESSED}({PROCESSED.stat().st_size:,} バイト)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
