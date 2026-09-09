"""立地の埋め込みを学ぶノイズ除去オートエンコーダ(SPEC §3.7 / §3.8)。

**標準化をモデルの中に入れてある。** `preprocessing.json` を読んで
TypeScript 側でも同じ標準化を書くと、二つの実装がずれても検査は緑のままになる
(HC-065)。境界を一つ減らし、ONNX に生の特徴を渡せばよいようにする。

潜在は 8 次元。入力が 16 次元しかないので、構想書 §16.3 の 64 次元は
圧縮ではなく拡張になり、そこでの余弦類似度は入力空間の回転にすぎない。
"""

from __future__ import annotations

import numpy as np
import torch
from torch import nn

LATENT_DIM = 8
HIDDEN_1 = 64
HIDDEN_2 = 32
DROPOUT = 0.15


class KofunEncoder(nn.Module):
    """生の(補完済み)特徴を受け取り、L2 正規化した埋め込みを返す。

    `forward` は埋め込みだけを返す —— これが ONNX へ出す形である。
    再構成は学習のときだけ `reconstruct` で使う。
    """

    def __init__(
        self,
        median: np.ndarray | torch.Tensor,
        iqr: np.ndarray | torch.Tensor,
        latent_dim: int = LATENT_DIM,
    ):
        super().__init__()
        median_t = torch.as_tensor(np.asarray(median), dtype=torch.float32)
        iqr_t = torch.as_tensor(np.asarray(iqr), dtype=torch.float32)
        if median_t.shape != iqr_t.shape or median_t.ndim != 1:
            raise ValueError(
                f"median と iqr は同じ長さの 1 次元: {median_t.shape} / {iqr_t.shape}"
            )
        if (iqr_t == 0).any():
            raise ValueError("iqr に 0 がある。0 の列は 1 に置き換えてから渡すこと")

        # 学習しない定数として持つ(ONNX にも一緒に載る)。
        self.register_buffer("median", median_t)
        self.register_buffer("iqr", iqr_t)

        n_features = int(median_t.shape[0])
        self.encoder = nn.Sequential(
            nn.Linear(n_features, HIDDEN_1),
            nn.GELU(),
            nn.LayerNorm(HIDDEN_1),
            nn.Dropout(DROPOUT),
            nn.Linear(HIDDEN_1, HIDDEN_2),
            nn.GELU(),
            nn.Linear(HIDDEN_2, latent_dim),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, HIDDEN_2),
            nn.GELU(),
            nn.Linear(HIDDEN_2, HIDDEN_1),
            nn.GELU(),
            nn.Linear(HIDDEN_1, n_features),
        )

    def standardise(self, raw: torch.Tensor) -> torch.Tensor:
        return (raw - self.median) / self.iqr

    def embed_standardised(self, scaled: torch.Tensor) -> torch.Tensor:
        latent = self.encoder(scaled)
        return nn.functional.normalize(latent, p=2.0, dim=1)

    def forward(self, raw: torch.Tensor) -> torch.Tensor:
        return self.embed_standardised(self.standardise(raw))

    def reconstruct(self, scaled: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """標準化済みの入力から (埋め込み, 再構成) を返す。学習用。"""
        embedding = self.embed_standardised(scaled)
        return embedding, self.decoder(embedding)


def embed_numpy(model: KofunEncoder, raw: np.ndarray) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        return model(torch.as_tensor(raw, dtype=torch.float32)).cpu().numpy()
