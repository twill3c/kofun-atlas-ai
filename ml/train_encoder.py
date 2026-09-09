"""立地の埋め込みを学習する。

    python ml/train_encoder.py

出力:
  artifacts/encoder.pt            学習済み重み(リポジトリに入れない)
  data/derived/embeddings.json    全件の埋め込み(同梱する)
  data/derived/encoder-metrics.json  較正の実測値

較正の判定規則は SPEC §3.9 に**測定より先に**書いてある。
ここでは測るだけで、結果に合わせて閾値を動かさない。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np
import torch
from torch import nn

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from kofun_atlas import features, model as model_mod  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "kofun.json"
ARTIFACTS = ROOT / "artifacts"
DERIVED = ROOT / "data" / "derived"
PUBLIC_DATA = ROOT / "public" / "data"

SEED = 42
BATCH_SIZE = 128
MAX_EPOCHS = 300
PATIENCE = 30
LR = 1e-3
WEIGHT_DECAY = 1e-4
VAL_FRACTION = 0.15
NOISE_NUMERIC = 0.10
NOISE_BINARY = 0.05
TOP_K = 20

BINARY_COLUMNS = ("is_group", "aspect_is_missing", "terrain_is_missing")


def _binary_mask(names: tuple[str, ...]) -> np.ndarray:
    return np.array([n in BINARY_COLUMNS for n in names])


def add_noise(
    batch: torch.Tensor, is_binary: torch.Tensor, generator: torch.Generator
) -> torch.Tensor:
    """入力の一部を隠す(構想書 §16.4)。標準化後なので 0 が『中央値』にあたる。"""
    noisy = batch.clone()
    rates = torch.where(
        is_binary,
        torch.full_like(is_binary, NOISE_BINARY, dtype=torch.float32),
        torch.full_like(is_binary, NOISE_NUMERIC, dtype=torch.float32),
    )
    draw = torch.rand(batch.shape, generator=generator, device=batch.device)
    noisy[draw < rates] = 0.0
    return noisy


def train(scaled: np.ndarray, names: tuple[str, ...], scaler, seed: int):
    torch.manual_seed(seed)
    generator = torch.Generator().manual_seed(seed)

    n = scaled.shape[0]
    order = torch.randperm(n, generator=generator).numpy()
    n_val = int(round(n * VAL_FRACTION))
    val_idx, train_idx = order[:n_val], order[n_val:]

    x = torch.as_tensor(scaled, dtype=torch.float32)
    x_train, x_val = x[train_idx], x[val_idx]
    is_binary = torch.as_tensor(_binary_mask(names))

    net = model_mod.KofunEncoder(np.asarray(scaler.median), np.asarray(scaler.iqr))
    optimiser = torch.optim.AdamW(net.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    loss_fn = nn.MSELoss()

    best = float("inf")
    best_state = None
    since_best = 0
    history = []

    for epoch in range(MAX_EPOCHS):
        net.train()
        perm = torch.randperm(x_train.shape[0], generator=generator)
        total = 0.0
        for start in range(0, x_train.shape[0], BATCH_SIZE):
            batch = x_train[perm[start : start + BATCH_SIZE]]
            noisy = add_noise(batch, is_binary, generator)
            _, reconstruction = net.reconstruct(noisy)
            loss = loss_fn(reconstruction, batch)
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
            total += loss.detach().item() * batch.shape[0]

        net.eval()
        with torch.no_grad():
            _, val_rec = net.reconstruct(x_val)
            val_loss = float(loss_fn(val_rec, x_val))
        history.append({"epoch": epoch, "train": total / x_train.shape[0], "val": val_loss})

        if val_loss < best - 1e-6:
            best, since_best = val_loss, 0
            best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
        else:
            since_best += 1
            if since_best >= PATIENCE:
                break

    assert best_state is not None
    net.load_state_dict(best_state)
    net.eval()
    return net, best, history


def pca_reconstruction_mse(scaled: np.ndarray, latent_dim: int) -> float:
    """同じ潜在次元の PCA の再構成 MSE を独立に計算する(SPEC §3.9 の対照)。"""
    centre = scaled.mean(axis=0)
    centred = scaled - centre
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    basis = vt[:latent_dim]
    reconstructed = centred @ basis.T @ basis + centre
    return float(((reconstructed - scaled) ** 2).mean())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--out-suffix", default="")
    args = parser.parse_args()

    records = features.load_records(PROCESSED)
    matrix, _, names = features.build_matrix(records)
    filled, medians = features.impute(matrix)
    scaler = features.ScalerParams.fit(filled, names)
    scaled = scaler.transform(filled)

    net, val_loss, history = train(scaled, names, scaler, args.seed)

    with torch.no_grad():
        embedding = net(torch.as_tensor(filled, dtype=torch.float32)).numpy()
        _, reconstruction = net.reconstruct(torch.as_tensor(scaled, dtype=torch.float32))
        ae_mse = float(((reconstruction.numpy() - scaled) ** 2).mean())

    pca_mse = pca_reconstruction_mse(scaled, model_mod.LATENT_DIM)
    baseline_neighbours = features.top_neighbours(scaled, TOP_K)
    ae_neighbours = features.top_neighbours(embedding, TOP_K)
    jaccard = features.mean_jaccard(ae_neighbours, baseline_neighbours)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    DERIVED.mkdir(parents=True, exist_ok=True)
    suffix = args.out_suffix
    torch.save(
        {
            "state_dict": net.state_dict(),
            "feature_names": list(names),
            "medians": medians.tolist(),
            "scaler": scaler.to_dict(),
            "seed": args.seed,
            "latent_dim": model_mod.LATENT_DIM,
        },
        ARTIFACTS / f"encoder{suffix}.pt",
    )

    # 既定の学習の埋め込みは出荷物なので public へ置く(Vercel は Python を持たない
    # ので、配るものはリポジトリに入っていなければならない)。
    # seed を変えた確認用の出力は手元だけのもので、同梱しない。
    embeddings_path = (
        PUBLIC_DATA / "embeddings.json" if not suffix else DERIVED / f"embeddings{suffix}.json"
    )
    embeddings_path.parent.mkdir(parents=True, exist_ok=True)
    embeddings_path.write_text(
        json.dumps(
            {
                "latent_dim": model_mod.LATENT_DIM,
                "feature_names": list(names),
                "ids": [r["id"] for r in records],
                "embeddings": [[round(v, 6) for v in row] for row in embedding.tolist()],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"埋め込み → {embeddings_path}")

    metrics = {
        "seed": args.seed,
        "records": len(records),
        "n_features": len(names),
        "latent_dim": model_mod.LATENT_DIM,
        "epochs_run": len(history),
        "val_mse": val_loss,
        "ae_reconstruction_mse": ae_mse,
        "pca_reconstruction_mse": pca_mse,
        "top20_jaccard_vs_baseline": jaccard,
    }
    (DERIVED / f"encoder-metrics{suffix}.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

    # SPEC §3.9 で先に宣言した判定規則。ここでは閾値を動かさない。
    print("--- SPEC §3.9 の判定 ---")
    print(
        f"G-20 代替性: Top-{TOP_K} Jaccard = {jaccard:.4f} "
        f"({'通過' if jaccard < 0.90 else '不通過 → 主張を降ろす'})"
    )
    print(
        f"G-21 非線形性: AE {ae_mse:.6f} vs PCA {pca_mse:.6f} "
        f"({'通過' if ae_mse <= pca_mse else '不通過 → 主張を降ろす'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
