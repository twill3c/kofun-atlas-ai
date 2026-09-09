"""T-047〜T-051: 学習済みエンコーダの一致・再現性・較正。

期待値の出所:
- T-047 / T-048: SPEC §7 G-08(`max_abs_error <= 1e-4`)
- T-049: SPEC §7 G-22(seed 固定で再現する)
- T-050 / T-051: **SPEC §3.9 で測定より先に宣言した判定規則**(G-20 / G-21)。
  結果に合わせて閾値を動かしていないことが、この検査の意味である。
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from kofun_atlas import features

pytestmark = pytest.mark.validation

PARITY_TOLERANCE = 1e-4
JACCARD_LIMIT = 0.90  # SPEC §3.9 G-20
TOP_K = 20


@pytest.fixture(scope="module")
def metrics(project_root, require_artifact):
    path = require_artifact(
        project_root / "data" / "derived" / "encoder-metrics.json",
        "`python ml/train_encoder.py` を先に実行すること",
    )
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def embeddings(project_root, require_artifact):
    path = require_artifact(
        project_root / "public" / "data" / "embeddings.json",
        "`python ml/train_encoder.py` を先に実行すること",
    )
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def onnx_session(project_root, require_artifact):
    path = require_artifact(
        project_root / "public" / "models" / "kofun_encoder.onnx",
        "`python ml/export_onnx.py` を先に実行すること",
    )
    ort = pytest.importorskip("onnxruntime")
    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def _raw_features(project_root):
    records = features.load_records(project_root / "data" / "processed" / "kofun.json")
    order = json.loads(
        (project_root / "public" / "models" / "feature-order.json").read_text(
            encoding="utf-8"
        )
    )
    matrix, _, names = features.build_matrix(records)
    assert list(names) == order["feature_names"], "特徴の並びが書き出し時と違う"
    filled, _ = features.impute(matrix, medians=order["medians"])
    return records, filled


# ---------------------------------------------------------------------- T-047


def test_t047_onnx_matches_pytorch(project_root, onnx_session, embeddings):
    """G-08: 学習時に保存した埋め込みと ONNX の出力が一致する。

    保存した埋め込みは PyTorch が出したものなので、これが二実装の照合になる。
    """
    _, filled = _raw_features(project_root)
    onnx_out = onnx_session.run(["embedding"], {"features": filled.astype(np.float32)})[0]
    stored = np.asarray(embeddings["embeddings"], dtype=np.float64)

    assert onnx_out.shape == stored.shape
    # 保存側は小数 6 桁へ丸めてあるので、丸め幅を許容に足す。
    tolerance = PARITY_TOLERANCE + 5e-7
    max_abs_error = float(np.abs(onnx_out - stored).max())
    assert max_abs_error <= tolerance, f"最大絶対差 {max_abs_error:.3e}"


def test_t047_embeddings_are_l2_normalised(embeddings):
    norms = np.linalg.norm(np.asarray(embeddings["embeddings"]), axis=1)
    np.testing.assert_allclose(norms, 1.0, atol=1e-5)


# ---------------------------------------------------------------------- T-048


def test_t048_positive_control_onnx_uses_its_input(project_root, onnx_session):
    """入力を変えると出力が変わる(定数を返していない)。"""
    _, filled = _raw_features(project_root)
    base = filled[:8].astype(np.float32)
    out_a = onnx_session.run(["embedding"], {"features": base})[0]

    moved = base.copy()
    moved[:, 0] += 100.0  # 標高だけを動かす
    out_b = onnx_session.run(["embedding"], {"features": moved})[0]

    assert not np.allclose(out_a, out_b, atol=1e-6), (
        "入力を変えても埋め込みが変わらない。ONNX が定数を返している"
    )


def test_t048_batch_axis_is_dynamic(project_root, onnx_session):
    """1 件でも 8 件でも同じ結果になる(バッチの組み方で出力が変わらない)。"""
    _, filled = _raw_features(project_root)
    batch = filled[:8].astype(np.float32)
    together = onnx_session.run(["embedding"], {"features": batch})[0]
    apart = np.vstack(
        [onnx_session.run(["embedding"], {"features": row[None, :]})[0] for row in batch]
    )
    np.testing.assert_allclose(together, apart, atol=1e-6)


# ---------------------------------------------------------------------- T-049


def test_t049_training_is_reproducible(project_root):
    """G-22: 同じ seed で二度学習した埋め込みが一致し、seed を変えると変わる。

    seed を変えた出力は**手元だけのもので同梱しない**(学習に 10 分かかり、
    CI では回せない)。無ければ skip する —— `KOFUN_REQUIRE_ARTIFACTS` でも
    落とさないのは、これが「作り忘れ」ではなく意図した不在だからである。
    実測結果は SPEC §3.9 に残す。
    """
    same = project_root / "data" / "derived" / "embeddings-seed42b.json"
    other = project_root / "data" / "derived" / "embeddings-seed7.json"
    if not same.exists() or not other.exists():
        pytest.skip("再現性の確認には --out-suffix を付けた 2 回の学習が要る(手元専用)")
    base = np.asarray(
        json.loads(
            (project_root / "public" / "data" / "embeddings.json").read_text(
                encoding="utf-8"
            )
        )["embeddings"]
    )
    repeat = np.asarray(json.loads(same.read_text(encoding="utf-8"))["embeddings"])
    different = np.asarray(json.loads(other.read_text(encoding="utf-8"))["embeddings"])

    np.testing.assert_allclose(base, repeat, atol=1e-6)
    assert not np.allclose(base, different, atol=1e-3), (
        "seed を変えても同じ埋め込みが出る。一致が seed 固定の結果だと言えない"
    )


# --------------------------------------------------------------- T-050 / T-051


def test_t050_embedding_is_not_substitutable_by_the_naive_baseline(metrics):
    """G-20: SPEC §3.9 で先に宣言した規則。閾値をここで動かさない。"""
    jaccard = metrics["top20_jaccard_vs_baseline"]
    assert jaccard < JACCARD_LIMIT, (
        f"AE の Top-{TOP_K} 近傍が標準化素性の余弦類似度と Jaccard {jaccard:.4f} で重なる。"
        "SPEC §3.9 に従い『AI が学習した埋め込み』という主張を降ろすこと"
    )


def test_t051_autoencoder_beats_pca_at_the_same_latent_dim(metrics):
    """G-21: 非線形性が効いていること。"""
    ae, pca = metrics["ae_reconstruction_mse"], metrics["pca_reconstruction_mse"]
    assert ae <= pca, (
        f"AE の再構成 MSE {ae:.6f} が PCA {pca:.6f} より悪い。"
        "SPEC §3.9 に従い非線形性の主張を降ろすこと"
    )


def test_t050_baseline_is_actually_different_from_the_embedding(project_root, embeddings):
    """対照が成り立つ前提の確認: 二つの近傍集合を実際に別々に計算している。

    同じものを二度計算していれば Jaccard は必ず 1.0 になり、T-050 は
    「重なっていない」ことを主張できない(HC-079)。
    """
    records = features.load_records(project_root / "data" / "processed" / "kofun.json")
    matrix, _, names = features.build_matrix(records)
    filled, _ = features.impute(matrix)
    scaler = features.ScalerParams.fit(filled, names)
    baseline = features.top_neighbours(scaler.transform(filled), TOP_K)
    learned = features.top_neighbours(np.asarray(embeddings["embeddings"]), TOP_K)

    assert baseline.shape == learned.shape
    assert not np.array_equal(baseline, learned), "二つの近傍集合が完全に同一"
    assert features.mean_jaccard(baseline, baseline.copy()) == pytest.approx(1.0)
