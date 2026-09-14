"""T-053〜T-055: 二次元配置。

期待値の出所: **SPEC §3.10 で測定より先に宣言した規則**(G-24 / G-25)と、
相似変換が順序を変えないという定義上の性質。
"""

from __future__ import annotations

import json

import numpy as np
import pytest

pytestmark = pytest.mark.validation

NEIGHBOURS = 20
SHUFFLED_MARGIN = 0.1  # SPEC §3.10 G-25


@pytest.fixture(scope="module")
def projection(project_root, require_artifact):
    path = require_artifact(
        project_root / "public" / "data" / "projection.json",
        "`python ml/build_projection.py` を先に実行すること",
    )
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics(project_root, require_artifact):
    path = require_artifact(
        project_root / "data" / "derived" / "projection-metrics.json",
        "`python ml/build_projection.py` を先に実行すること",
    )
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def embeddings(project_root, require_artifact):
    path = require_artifact(
        project_root / "public" / "data" / "embeddings.json",
        "`python ml/train_encoder.py` を先に実行すること",
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_t053_projection_covers_every_record(projection, embeddings):
    assert projection["ids"] == embeddings["ids"], "並びが埋め込みと違う"
    assert len(projection["xy"]) == len(projection["ids"])


def test_t053_coordinates_are_finite_and_normalised(projection):
    xy = np.asarray(projection["xy"], dtype=float)
    assert np.isfinite(xy).all(), "有限でない座標がある"
    # 表示の都合で -1..1 へ収めてある(相似変換なので順序は変わらない)。
    assert np.abs(xy).max() == pytest.approx(1.0, abs=1e-4)
    assert xy.shape[1] == 2


def test_t054_neighbourhood_preservation_beats_pca(metrics):
    """G-24: 宣言した指標で PCA-2 を上回る。閾値をここで動かさない。"""
    assert metrics["trustworthiness"] > metrics["trustworthiness_pca2"], (
        f"t-SNE {metrics['trustworthiness']:.4f} が "
        f"PCA-2 {metrics['trustworthiness_pca2']:.4f} を上回らない"
    )


def test_t055_positive_control_shuffled_layout_is_clearly_worse(metrics):
    """G-25: 並べ替えた配置が明確に低い。低くなければこの指標は何も測っていない。"""
    assert metrics["trustworthiness_shuffled"] < metrics["trustworthiness"] - SHUFFLED_MARGIN, (
        f"並べ替え {metrics['trustworthiness_shuffled']:.4f} が "
        f"採用値 {metrics['trustworthiness']:.4f} と近すぎる"
    )
    # 対照が成り立つ前提: 並べ替えは実際に別の配置になっている。
    assert metrics["trustworthiness_shuffled"] < 0.7


def test_t055_recomputed_trustworthiness_matches_the_recorded_value(
    projection, embeddings, metrics, require_module
):
    """記録した数値を、**実際に配った座標**から計算し直して突き合わせる(HC-152)。

    正規化そのものは相似変換なので trustworthiness を変えない。変えるのは
    **配るときの丸め**(小数 5 桁)で、僅差の近傍の順序が入れ替わることがある。
    実測 2026-09-10 で差は 3.5e-6。許容差はこの実測から置いた —— 丸めた後の
    値で確かめる、という規律の一部である(HC-240)。
    """
    require_module("sklearn")  # 無ければ手元は skip・CI は失敗(validate 追加依存)
    from sklearn.manifold import trustworthiness

    emb = np.asarray(embeddings["embeddings"], dtype=float)
    xy = np.asarray(projection["xy"], dtype=float)
    recomputed = trustworthiness(emb, xy, n_neighbors=NEIGHBOURS)
    assert recomputed == pytest.approx(metrics["trustworthiness"], abs=1e-4)
    assert recomputed == pytest.approx(projection["trustworthiness"], abs=5e-5)


def test_t055_clustering_is_not_shipped(project_root):
    """SPEC §3.11: G-23 不通過によりクラスタ機能は落とした。

    落としたはずのものが黙って戻っていないことを確かめる。
    """
    assert not (project_root / "public" / "data" / "clusters.json").exists(), (
        "クラスタを配っている。SPEC §3.11 の結論と食い違う"
    )
    projection_payload = json.loads(
        (project_root / "public" / "data" / "projection.json").read_text(encoding="utf-8")
    )
    assert "clusters" not in projection_payload
    assert "labels" not in projection_payload
