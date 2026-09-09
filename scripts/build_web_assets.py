"""Web が読む静的アセットを生成する。

**画面に出す数値をソースへ直接書かない**ため —— 文書やコードに書いた数は
実装のテストでは守られない(HC-152)。数はここで一箇所から作り、画面はそれを読む。

    python scripts/build_web_assets.py

`data/processed/kofun.json` があればそれを、無ければ `data/interim/kofun_l0.json` を
数える。どちらを数えたかは `stage` に出す。
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from kofun_atlas import geocode, geoshape  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "kofun.json"
INTERIM = ROOT / "data" / "interim" / "kofun_l0.json"
GEOSHAPE_MANIFEST = ROOT / "data" / "raw" / "geoshape" / "manifest.json"
GSI_MANIFEST = ROOT / "data" / "raw" / "gsi" / "manifest.json"
TERRAIN_MANIFEST = ROOT / "data" / "derived" / "manifest.json"
ENCODER_METRICS = ROOT / "data" / "derived" / "encoder-metrics.json"
EMBEDDINGS = ROOT / "public" / "data" / "embeddings.json"
OUT = ROOT / "public" / "data" / "data-manifest.json"

MODEL_VERSION = "kofun-location-v1.0.0"


def main() -> int:
    if PROCESSED.exists():
        source_path, stage = PROCESSED, "L1"
    elif INTERIM.exists():
        source_path, stage = INTERIM, "L0"
    else:
        print("レコードが無い。先に scripts/normalize.py を実行すること", file=sys.stderr)
        return 1

    rows = json.loads(source_path.read_text(encoding="utf-8"))
    geoshape_manifest = json.loads(GEOSHAPE_MANIFEST.read_text(encoding="utf-8"))

    sources = [
        {
            "id": geoshape.SOURCE_ID,
            "role": "位置・名称・読み・住所",
            "source_version": geoshape_manifest["source_version"],
            "retrieved_at": geoshape_manifest["retrieved_at"],
            "license": geoshape_manifest["license"],
            "credit": geoshape_manifest["credit"],
            "sha256": geoshape_manifest["sha256"],
        }
    ]
    if GSI_MANIFEST.exists():
        gsi = json.loads(GSI_MANIFEST.read_text(encoding="utf-8"))
        sources.append(
            {
                "id": geocode.SOURCE_ID,
                "role": "都道府県・市区町村",
                "retrieved_at": gsi["retrieved_at"],
                "license": gsi["license"],
                "credit": gsi["credit"],
                "coordinates": gsi["coordinates"],
            }
        )

    if TERRAIN_MANIFEST.exists():
        terrain = json.loads(TERRAIN_MANIFEST.read_text(encoding="utf-8"))
        sources.append(
            {
                "id": terrain["source"],
                "role": "地形特徴(標高・傾斜・起伏)",
                "retrieved_at": terrain["generated_at"],
                "license": terrain["license"],
                "credit": terrain["credit"],
                "zoom": terrain["zoom"],
                "radius_m": terrain["radius_m"],
            }
        )
        stage = "L2"

    embedding_count = 0
    model_version = None
    if EMBEDDINGS.exists() and ENCODER_METRICS.exists():
        embeddings = json.loads(EMBEDDINGS.read_text(encoding="utf-8"))
        metrics = json.loads(ENCODER_METRICS.read_text(encoding="utf-8"))
        embedding_count = len(embeddings["embeddings"])
        model_version = MODEL_VERSION
        sources.append(
            {
                "id": "kofun_location_encoder",
                "role": "立地の類似度(AI)",
                "retrieved_at": dt.date.today().isoformat(),
                "license": "MIT(モデル) / 出典は上記の派生",
                "credit": (
                    f"立地の埋め込み {metrics['latent_dim']} 次元・"
                    f"seed {metrics['seed']}・入力 {metrics['n_features']} 次元"
                ),
            }
        )
        stage = "L3"

    manifest = {
        "version": dt.date.today().isoformat(),
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "stage": stage,
        "shipped": False,
        "counts": {
            "geoshape_rows": geoshape_manifest["kofun_candidates"],
            "merged_duplicate_rows": sum(
                len(r["raw_extra"].get("geoshape_duplicate_ids", [])) for r in rows
            ),
            "records": len(rows),
            "with_prefecture": sum(1 for r in rows if r["prefecture"]),
            "without_muni_cd": sum(1 for r in rows if r.get("muni_cd") is None),
            "with_coordinates": sum(
                1 for r in rows if r["location"]["lat"] is not None
            ),
            "with_mound_type": sum(1 for r in rows if r["mound"]["type"] != "unknown"),
            "with_chronology": sum(
                1 for r in rows if r["chronology"]["year_min"] is not None
            ),
            "prefecture_corrected": sum(
                1
                for r in rows
                if r.get("muni_cd")
                and int(r["muni_cd"][:2]) != int(r["raw_extra"]["geoshape_pref_code"])
            ),
            "with_elevation": sum(
                1 for r in rows if (r.get("terrain") or {}).get("elevation_m") is not None
            ),
            "with_slope": sum(
                1 for r in rows if (r.get("terrain") or {}).get("slope_deg") is not None
            ),
            "with_embedding": embedding_count,
        },
        "prefectures": dict(
            sorted(collections.Counter(r["prefecture"] for r in rows if r["prefecture"]).items())
        ),
        "review_status": dict(
            sorted(collections.Counter(r["quality"]["review_status"] for r in rows).items())
        ),
        "sources": sources,
        "model_version": model_version,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    printable = {k: v for k, v in manifest.items() if k != "prefectures"}
    printable["prefectures"] = f"{len(manifest['prefectures'])} 種"
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
