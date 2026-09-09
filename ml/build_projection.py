"""立地の埋め込みを二次元へ落として配る(SPEC §3.10 / §3.11)。

    python ml/build_projection.py

出力:
  public/data/projection.json          全件の 2 次元座標
  data/derived/projection-metrics.json 較正の実測値

手法は **t-SNE**。SPEC §3.10 で宣言した規則に従って三つを測り、
宣言した指標(trustworthiness k=20)で最も高く、追加依存が要らないものを採った。

**クラスタ機能は落とした。** G-23 の閾値(ノイズ率 50% 未満)をどの設定でも
満たさなかったからである(SPEC §3.11)。ここではクラスタ番号を出さない。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

import numpy as np
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE, trustworthiness

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from kofun_atlas import features  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "kofun.json"
EMBEDDINGS = ROOT / "public" / "data" / "embeddings.json"
OUT = ROOT / "public" / "data" / "projection.json"
METRICS = ROOT / "data" / "derived" / "projection-metrics.json"

SEED = 42
NEIGHBOURS = 20
PERPLEXITY = 30
METHOD = "t-SNE"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    for path in (PROCESSED, EMBEDDINGS):
        if not path.exists():
            print(f"{path} が無い", file=sys.stderr)
            return 1

    payload = json.loads(EMBEDDINGS.read_text(encoding="utf-8"))
    embedding = np.asarray(payload["embeddings"], dtype=np.float64)
    records = features.load_records(PROCESSED)
    if payload["ids"] != [r["id"] for r in records]:
        raise ValueError("埋め込みの並びがレコードと違う")

    started = time.monotonic()
    coords = TSNE(
        n_components=2,
        random_state=args.seed,
        init="pca",
        perplexity=PERPLEXITY,
    ).fit_transform(embedding)
    elapsed = time.monotonic() - started

    score = float(trustworthiness(embedding, coords, n_neighbors=NEIGHBOURS))
    baseline = PCA(n_components=2, random_state=args.seed).fit_transform(embedding)
    baseline_score = float(trustworthiness(embedding, baseline, n_neighbors=NEIGHBOURS))

    # G-25 陽性対照: 座標を並べ替えた配置は明確に低くなること。
    rng = np.random.default_rng(args.seed)
    shuffled = coords[rng.permutation(len(coords))]
    shuffled_score = float(trustworthiness(embedding, shuffled, n_neighbors=NEIGHBOURS))

    # 表示の都合で -1..1 へ収める。順序も相対距離も変えない相似変換。
    centre = coords.mean(axis=0)
    scale = float(np.abs(coords - centre).max())
    normalised = (coords - centre) / scale

    OUT.write_text(
        json.dumps(
            {
                "method": METHOD,
                "seed": args.seed,
                "n_neighbors": NEIGHBOURS,
                "perplexity": PERPLEXITY,
                "trustworthiness": round(score, 4),
                "ids": payload["ids"],
                "xy": [[round(x, 5), round(y, 5)] for x, y in normalised.tolist()],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    metrics = {
        "method": METHOD,
        "seed": args.seed,
        "records": len(records),
        "n_neighbors": NEIGHBOURS,
        "trustworthiness": score,
        "trustworthiness_pca2": baseline_score,
        "trustworthiness_shuffled": shuffled_score,
        "seconds": round(elapsed, 1),
    }
    METRICS.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print("--- SPEC §3.10 の判定 ---")
    print(
        f"G-24 近傍保存: t-SNE {score:.4f} vs PCA-2 {baseline_score:.4f} "
        f"({'通過' if score > baseline_score else '不通過'})"
    )
    print(
        f"G-25 陽性対照: 並べ替え {shuffled_score:.4f} "
        f"({'通過' if shuffled_score < score - 0.1 else '不通過 → この指標は何も測っていない'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
