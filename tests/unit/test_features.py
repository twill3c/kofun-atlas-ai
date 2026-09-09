"""T-044〜T-046: 特徴行列・標準化・循環量の符号化。

期待値の出所: **閉形式**と SPEC §3.8。
標準化は既知の分布(等差数列)で中央値と IQR を手計算し、等号で比べる。
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kofun_atlas import features

pytestmark = pytest.mark.unit


def _record(name="甲古墳", lat=34.5, lon=135.8, **terrain):
    base = {
        "elevation_m": 100.0,
        "slope_deg": 5.0,
        "aspect_deg": 90.0,
        "local_relief_250m": 10.0,
        "local_relief_500m": 20.0,
        "local_relief_1000m": 30.0,
        "relative_elevation_500m": 1.0,
        "tri": 2.0,
        "openness_500m": 0.5,
    }
    base.update(terrain)
    return {"name": name, "location": {"lat": lat, "lon": lon}, "terrain": base}


# ---------------------------------------------------------------------- T-044


def test_t044_matrix_shape_and_column_order():
    records = [_record(), _record(name="乙古墳群", lat=34.6)]
    matrix, mask, names = features.build_matrix(records)
    assert matrix.shape == (2, len(features.FEATURE_NAMES))
    assert names == features.FEATURE_NAMES
    assert mask.shape == matrix.shape


def test_t044_prefecture_is_not_an_input():
    """SPEC §3.8: 地域を学ばせないために都道府県を入力に入れない。"""
    assert not any("pref" in n for n in features.FEATURE_NAMES)
    assert not any(n in ("lat", "lon") for n in features.FEATURE_NAMES)


def test_t044_missing_is_flagged_not_zeroed():
    """欠測は 0 で埋めず、マスクを立てる(構想書 §19.2)。"""
    records = [_record(), _record(name="乙古墳", lat=34.6, elevation_m=None, aspect_deg=None)]
    matrix, mask, names = features.build_matrix(records)
    i_elev = names.index("elevation_m")
    i_terr = names.index("terrain_is_missing")
    i_asp = names.index("aspect_is_missing")

    assert np.isnan(matrix[1, i_elev]), "欠測がこの段階で 0 になっている"
    assert mask[1, i_elev]
    assert matrix[1, i_terr] == 1.0
    assert matrix[1, i_asp] == 1.0
    assert matrix[0, i_terr] == 0.0


def test_t044_imputation_uses_the_median_not_zero():
    """補完値が実際に中央値と一致する。"""
    column = np.array([[1.0], [3.0], [np.nan], [5.0], [11.0]])
    filled, medians = features.impute(column)
    expected = float(np.median([1.0, 3.0, 5.0, 11.0]))  # 4.0
    assert medians[0] == pytest.approx(expected)
    assert filled[2, 0] == pytest.approx(expected)
    assert filled[2, 0] != 0.0


def test_t044_imputation_can_reuse_training_medians():
    """推論時は学習時の中央値を使う(データが変わっても補完値は動かない)。"""
    column = np.array([[np.nan]])
    filled, _ = features.impute(column, medians=[7.0])
    assert filled[0, 0] == pytest.approx(7.0)


def test_t044_is_group_reads_the_name():
    records = [_record(name="甲古墳"), _record(name="乙古墳群", lat=34.6)]
    matrix, _, names = features.build_matrix(records)
    i = names.index("is_group")
    assert matrix[0, i] == 0.0
    assert matrix[1, i] == 1.0


# ---------------------------------------------------------------------- T-045


def test_t045_scaler_matches_the_hand_computed_median_and_iqr():
    """等差数列 0..8 なら中央値 4、第 1 四分位 2、第 3 四分位 6、IQR 4。"""
    column = np.arange(9, dtype=float).reshape(-1, 1)
    assert float(np.median(column)) == 4.0
    assert float(np.percentile(column, 25)) == 2.0
    assert float(np.percentile(column, 75)) == 6.0

    scaler = features.ScalerParams.fit(column, ("x",))
    assert scaler.median == (4.0,)
    assert scaler.iqr == (4.0,)

    scaled = scaler.transform(column)
    assert scaled[0, 0] == pytest.approx(-1.0)
    assert scaled[4, 0] == pytest.approx(0.0)
    assert scaled[8, 0] == pytest.approx(1.0)


def test_t045_constant_column_does_not_divide_by_zero():
    column = np.full((5, 1), 3.0)
    scaler = features.ScalerParams.fit(column, ("x",))
    assert scaler.iqr == (1.0,)
    scaled = scaler.transform(column)
    assert np.isfinite(scaled).all()
    assert (scaled == 0.0).all()


def test_t045_scaler_round_trips_through_json():
    column = np.arange(9, dtype=float).reshape(-1, 1)
    scaler = features.ScalerParams.fit(column, ("x",))
    again = features.ScalerParams.from_dict(scaler.to_dict())
    assert again == scaler


def test_t045_transform_rejects_a_wrong_column_count():
    scaler = features.ScalerParams.fit(np.zeros((3, 2)), ("a", "b"))
    with pytest.raises(ValueError):
        scaler.transform(np.zeros((3, 3)))


# ---------------------------------------------------------------------- T-046


def test_t046_aspect_is_encoded_so_that_north_wraps_around():
    """359 度と 1 度は近く、179 度と 181 度より近くない、ということはない。

    循環符号化の要点は **0 度と 360 度が同じ場所になる**こと。
    素の角度を入れると 359 と 1 が最も遠い 2 点になる。
    """
    def vec(deg):
        matrix, _, names = features.build_matrix([_record(aspect_deg=deg)])
        i, j = names.index("aspect_sin"), names.index("aspect_cos")
        return np.array([matrix[0, i], matrix[0, j]])

    near = np.linalg.norm(vec(359.0) - vec(1.0))
    far = np.linalg.norm(vec(0.0) - vec(180.0))
    assert near < far
    assert near == pytest.approx(2 * math.sin(math.radians(1.0)), abs=1e-9)

    # 素の角度なら 359 と 1 は最も遠い。循環符号化がそれを直していることの対照。
    assert abs(359.0 - 1.0) > abs(0.0 - 180.0)


def test_t046_missing_aspect_is_zero_vector_with_a_flag():
    matrix, _, names = features.build_matrix([_record(aspect_deg=None)])
    i, j = names.index("aspect_sin"), names.index("aspect_cos")
    filled, _ = features.impute(matrix, medians=[0.0] * len(names))
    assert filled[0, i] == 0.0 and filled[0, j] == 0.0
    assert matrix[0, names.index("aspect_is_missing")] == 1.0


# --------------------------------------------------------- 空間文脈(補助)


def test_t044_spatial_context_counts_neighbours():
    """1 km 以内と 5 km 以内の数え方が距離と整合する。"""
    # 緯度 0.01 度 ≈ 1.11 km、0.001 度 ≈ 111 m。
    records = [
        _record(name="中心", lat=34.5000, lon=135.8),
        _record(name="近い", lat=34.5010, lon=135.8),  # 約 111 m
        _record(name="遠い", lat=34.6000, lon=135.8),  # 約 11 km
    ]
    context = features.spatial_context(records)
    assert context[0]["nearest_kofun_m"] == pytest.approx(111.0, rel=0.05)
    assert context[0]["kofun_within_1km"] == 1
    assert context[0]["kofun_within_5km"] == 1
    assert context[2]["kofun_within_5km"] == 0


def test_t044_mean_jaccard_is_one_for_identical_sets():
    a = np.array([[1, 2, 3], [4, 5, 6]])
    assert features.mean_jaccard(a, a.copy()) == pytest.approx(1.0)
    b = np.array([[7, 8, 9], [4, 5, 6]])
    assert features.mean_jaccard(a, b) == pytest.approx(0.5)


# ------------------------------------------ T-052: 同じ代表点と近さを混ぜない


def test_t052_coincident_records_do_not_become_zero_distance_neighbours():
    """同じ代表点に記録された別レコードを「最近傍 0 m」にしない。

    Geoshape は古墳群にひとつの代表点を与えるので、座標のまったく同じ
    レコードが実データに 181 件(80 組・2026-09-10 実測)ある。これを
    最近傍距離 0 m として入れると `log1p(0) = 0` の縮退した山ができ、
    クラスタリングが立地でなく**記録の重なり**を拾う。
    """
    records = [
        _record(name="甲古墳", lat=34.5000, lon=135.8),
        _record(name="甲古墳群", lat=34.5000, lon=135.8),  # まったく同じ点
        _record(name="乙古墳", lat=34.5010, lon=135.8),  # 約 111 m
    ]
    context = features.spatial_context(records)

    # 同じ点の相手は最近傍から外れ、次に近い実点までの距離になる。
    assert context[0]["nearest_kofun_m"] == pytest.approx(111.0, rel=0.05)
    assert context[1]["nearest_kofun_m"] == pytest.approx(111.0, rel=0.05)
    assert context[2]["nearest_kofun_m"] == pytest.approx(111.0, rel=0.05)

    # 共有していることは別の二値で残す(捨てない)。
    assert context[0]["shares_coordinates"] == 1.0
    assert context[1]["shares_coordinates"] == 1.0
    assert context[2]["shares_coordinates"] == 0.0

    # 数のほうは同じ点の相手も数える(「近くにいくつ記録があるか」だから)。
    assert context[0]["kofun_within_1km"] == 2


def test_t052_positive_control_zero_distance_would_be_degenerate():
    """対照: 同じ点を除かなければ log1p(0) = 0 の縮退が起きる。

    この検査が守っている性質そのものを、対照側で明示しておく。
    """
    assert math.log1p(0.0) == 0.0
    records = [
        _record(name="甲古墳", lat=34.5, lon=135.8),
        _record(name="乙古墳", lat=34.5, lon=135.8),
    ]
    matrix, _, names = features.build_matrix(records)
    column = matrix[:, names.index("log_nearest_kofun_m")]
    assert not np.any(column == 0.0), "縮退した 0 が残っている"


def test_t052_shares_coordinates_is_a_feature():
    assert "shares_coordinates" in features.FEATURE_NAMES
