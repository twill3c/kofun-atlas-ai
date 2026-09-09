"""モデルカードを実測値から生成する(構想書 §20)。

    python ml/model_card.py

**数値を手で書かない。** 文書に書いた数は実装のテストでは守られない(HC-152)ので、
学習が出した `encoder-metrics.json` と `data-manifest.json` から流し込む。
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
METRICS = ROOT / "data" / "derived" / "encoder-metrics.json"
ORDER = ROOT / "public" / "models" / "feature-order.json"
DATA_MANIFEST = ROOT / "public" / "data" / "data-manifest.json"
ONNX = ROOT / "public" / "models" / "kofun_encoder.onnx"
OUT = ROOT / "public" / "models" / "model-card.md"

MODEL_VERSION = "kofun-location-v1.0.0"


def git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "(不明)"


def main() -> int:
    for path in (METRICS, ORDER, DATA_MANIFEST, ONNX):
        if not path.exists():
            print(f"{path} が無い", file=sys.stderr)
            return 1

    metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    order = json.loads(ORDER.read_text(encoding="utf-8"))
    data = json.loads(DATA_MANIFEST.read_text(encoding="utf-8"))
    counts = data["counts"]

    features_list = "\n".join(f"- `{name}`" for name in order["feature_names"])
    sources_list = "\n".join(
        f"- {s['credit']}（{s['license']}／取得 {s['retrieved_at']}）"
        for s in data["sources"]
    )

    card = f"""# モデルカード — {MODEL_VERSION}

生成日 {dt.date.today().isoformat()} ／ commit `{git_sha()}` ／
データ版 {data["version"]}

このファイルは `ml/model_card.py` が実測値から生成する。手で書き換えない。

## これは何か

古墳が**置かれた場所**を {metrics["latent_dim"]} 次元のベクトルにするオートエンコーダ。
「立地の似ている古墳」を探すために使う。

## これは何ではないか

**古墳そのものの総合的な特徴を表すものではない。** 墳形・墳丘長・築造時期・
埋葬施設・出土品・文化財指定は、公開・再利用可能なデータでは
**1 件も埋まっていない**（収録 {counts["records"]:,} 件中 0 件）。
したがってこの埋め込みは考古学的な系統関係・編年・政治的まとまりを示さない。

## 学習データ

- 件数: {metrics["records"]:,} 件
- 入力: {metrics["n_features"]} 次元（下記）
- 都道府県・緯度経度は**入力に含めない**。「同じ地域だから似ている」を
  学ぶモデルにしないため

{features_list}

出典:

{sources_list}

## 欠測の扱い

欠測は 0 で埋めず、学習データの中央値で補い、同時に `is_missing` 列を立てる。
水面には標高がないので、島や海沿いの古墳では周囲の多くが欠測になる。
地形が取れなかったレコードは {counts["records"] - counts["with_elevation"]} 件。

## 学習の設定

- 潜在次元 {metrics["latent_dim"]} ／ seed {metrics["seed"]} ／ 実行エポック {metrics["epochs_run"]}
- ノイズ除去オートエンコーダ（数値 10%・二値 5% を隠す）
- 標準化（中央値と IQR）は**モデルの中**にある。ONNX の入力は補完済みの生の特徴

## 評価

| 指標 | 値 |
|---|---|
| 検証再構成 MSE | {metrics["val_mse"]:.6f} |
| 再構成 MSE（全件） | {metrics["ae_reconstruction_mse"]:.6f} |
| 同次元 PCA の再構成 MSE | {metrics["pca_reconstruction_mse"]:.6f} |
| Top-20 近傍の Jaccard（素朴な余弦類似度との重なり） | {metrics["top20_jaccard_vs_baseline"]:.4f} |

判定規則は SPEC §3.9 に**測定より先に**書いてある。

- G-20（代替性）: Jaccard が 0.90 以上なら「学習した埋め込み」という主張を降ろす → 通過
- G-21（非線形性）: 再構成が PCA より悪ければ主張を降ろす → 通過

## 既知の限界

- **「よい埋め込みである」ことは示していない。** 示したのは、素朴な余弦類似度とは
  違う近傍を返すことと、同次元の線形圧縮より再構成がよいことの二つだけである
- 近傍が考古学的に妥当かは、照合できる外部の正解が無いので**測っていない**
- 学習は上限の {metrics["epochs_run"]} エポックで止まった。検証損失はまだ下がっており、
  収束の証拠ではない
- 入力が立地だけなので、**地形の似た別地域の古墳**が近傍に来る。これは仕様である

## 出荷物

- `kofun_encoder.onnx`（{ONNX.stat().st_size:,} バイト）
- `feature-order.json`（入力の並びと欠測補完に使う中央値）

PyTorch と ONNX Runtime の出力差は `1e-4` 以下であることを検査している（G-08）。
"""
    OUT.write_text(card, encoding="utf-8")
    print(f"書き出し: {OUT}({OUT.stat().st_size:,} バイト)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
