"""学習済みエンコーダを ONNX へ書き出し、PyTorch との一致を確かめる。

    python ml/export_onnx.py

標準化はモデルの中にあるので、ONNX の入力は**補完済みの生の特徴**である。
`preprocessing.json` を読んで TypeScript 側でも標準化を書き直す必要はない。
書き直すと、二つの実装がずれても検査が緑のままになる(HC-065)。

`dynamo=False` は**意図して明示している**。torch 2.9 以降は torch.export を使う
新しい書き出しが既定になったが、それには `onnxscript` が要る(この環境には無い)。
既定に任せると torch を上げた日にグラフが黙って変わるので、旧経路に固定する。
新経路への移行は V1.1 で、そのときも G-08 の一致で確かめる。
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import onnxruntime as ort
import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from kofun_atlas import features, model as model_mod  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "kofun.json"
CHECKPOINT = ROOT / "artifacts" / "encoder.pt"
OUT_DIR = ROOT / "public" / "models"
ONNX_PATH = OUT_DIR / "kofun_encoder.onnx"
ORDER_PATH = OUT_DIR / "feature-order.json"

PARITY_TOLERANCE = 1e-4  # SPEC §7 G-08
OPSET = 18


def load_model() -> tuple[model_mod.KofunEncoder, dict]:
    checkpoint = torch.load(CHECKPOINT, map_location="cpu", weights_only=True)
    scaler = features.ScalerParams.from_dict(checkpoint["scaler"])
    net = model_mod.KofunEncoder(
        np.asarray(scaler.median), np.asarray(scaler.iqr), checkpoint["latent_dim"]
    )
    net.load_state_dict(checkpoint["state_dict"])
    net.eval()
    return net, checkpoint


def main() -> int:
    if not CHECKPOINT.exists():
        print(f"{CHECKPOINT} が無い。先に ml/train_encoder.py を実行すること", file=sys.stderr)
        return 1

    net, checkpoint = load_model()
    records = features.load_records(PROCESSED)
    matrix, _, names = features.build_matrix(records)
    if list(names) != checkpoint["feature_names"]:
        raise ValueError("特徴の並びが学習時と違う。ONNX の入力順が壊れる")
    filled, _ = features.impute(matrix, medians=checkpoint["medians"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dummy = torch.as_tensor(filled[:2], dtype=torch.float32)
    torch.onnx.export(
        net,
        (dummy,),
        str(ONNX_PATH),
        input_names=["features"],
        output_names=["embedding"],
        dynamic_axes={"features": {0: "batch"}, "embedding": {0: "batch"}},
        opset_version=OPSET,
        dynamo=False,
    )

    session = ort.InferenceSession(str(ONNX_PATH), providers=["CPUExecutionProvider"])
    onnx_out = session.run(
        ["embedding"], {"features": filled.astype(np.float32)}
    )[0]
    with torch.no_grad():
        torch_out = net(torch.as_tensor(filled, dtype=torch.float32)).numpy()

    max_abs_error = float(np.abs(onnx_out - torch_out).max())
    ORDER_PATH.write_text(
        json.dumps(
            {
                "feature_names": list(names),
                "medians": list(checkpoint["medians"]),
                "latent_dim": checkpoint["latent_dim"],
                "note": (
                    "標準化は ONNX の中にある。ここに載せる medians は欠測の補完にだけ使う。"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    size_mb = ONNX_PATH.stat().st_size / 1_048_576
    print(f"書き出し: {ONNX_PATH}({ONNX_PATH.stat().st_size:,} バイト / {size_mb:.2f} MB)")
    print(f"PyTorch と ONNX の最大絶対差: {max_abs_error:.3e}(基準 {PARITY_TOLERANCE:.0e})")
    if max_abs_error > PARITY_TOLERANCE:
        print("G-08 不通過", file=sys.stderr)
        return 1
    print("G-08 通過")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
