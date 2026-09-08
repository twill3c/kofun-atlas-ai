"""Web が読む静的アセットを生成する。

L0 では `public/data/data-manifest.json` だけを作る。
**画面に出す数値をソースへ直接書かない**ため —— 文書やコードに書いた数は
実装のテストでは守られない(HC-152)。数はここで一箇所から作り、画面はそれを読む。

    python scripts/build_web_assets.py
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from kofun_atlas import geoshape  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim" / "kofun_l0.json"
GEOSHAPE_MANIFEST = ROOT / "data" / "raw" / "geoshape" / "manifest.json"
OUT = ROOT / "public" / "data" / "data-manifest.json"


def main() -> int:
    if not INTERIM.exists():
        print(f"{INTERIM} が無い。先に scripts/normalize.py を実行すること", file=sys.stderr)
        return 1

    normalized = json.loads(INTERIM.read_text(encoding="utf-8"))
    geoshape_manifest = json.loads(GEOSHAPE_MANIFEST.read_text(encoding="utf-8"))

    merged_rows = sum(
        len(r["raw_extra"].get("geoshape_duplicate_ids", [])) for r in normalized
    )
    stages = collections.Counter(r["quality"]["review_status"] for r in normalized)

    manifest = {
        "version": dt.date.today().isoformat(),
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "stage": "L0",
        "shipped": False,
        "counts": {
            "geoshape_rows": geoshape_manifest["kofun_candidates"],
            "merged_duplicate_rows": merged_rows,
            "records": len(normalized),
            "with_prefecture": sum(1 for r in normalized if r["prefecture"]),
            "with_coordinates": sum(
                1 for r in normalized if r["location"]["lat"] is not None
            ),
            "with_mound_type": sum(
                1 for r in normalized if r["mound"]["type"] != "unknown"
            ),
            "with_chronology": sum(
                1 for r in normalized if r["chronology"]["year_min"] is not None
            ),
        },
        "review_status": dict(sorted(stages.items())),
        "sources": [
            {
                "id": geoshape.SOURCE_ID,
                "source_version": geoshape_manifest["source_version"],
                "retrieved_at": geoshape_manifest["retrieved_at"],
                "license": geoshape_manifest["license"],
                "credit": geoshape_manifest["credit"],
                "sha256": geoshape_manifest["sha256"],
            }
        ],
        "model_version": None,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
