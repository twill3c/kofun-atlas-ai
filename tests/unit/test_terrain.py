"""T-030〜T-035 / T-038: 地形特徴の算出器を解析解で検算する。

期待値の出所: **閉形式**。傾き既知の平面 `h = a·X + b·Y + c`(X は東、Y は北、単位 m)を
合成し、算出器の出力を解析解と突き合わせる。平面では Horn の有限差分が厳密になるので、
近似ではなく等号で比べられる。

導出は各テストの中で近傍ごとに検算してから使う(HC-004: 導出前提を assert で固定する)。
合成データは算出器を一切使わずに作る —— 実装から作ると恒等式になる(HC-045)。
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kofun_atlas import terrain

pytestmark = pytest.mark.unit


def plane(size: int, mpp: float, a: float, b: float, c: float = 100.0) -> np.ndarray:
    """`h = a·X + b·Y + c` の格子。行 i は南へ、列 j は東へ増える。

    X = j·mpp(東)、Y = -i·mpp(北)。中心は size//2。
    """
    assert size % 2 == 1, "中心画素を持つよう奇数にする"
    half = size // 2
    j = np.arange(size) - half
    i = np.arange(size) - half
    east = j[None, :] * mpp
    north = -i[:, None] * mpp
    return a * east + b * north + c


# ---------------------------------------------------------------- T-030 / T-032


@pytest.mark.parametrize(
    "a, b, expected_aspect",
    [
        (0.10, 0.0, 270.0),  # 東へ上る → 下りは西
        (-0.10, 0.0, 90.0),  # 西へ上る → 下りは東
        (0.0, 0.10, 180.0),  # 北へ上る → 下りは南
        (0.0, -0.10, 0.0),  # 南へ上る → 下りは北
        (0.10, 0.10, 225.0),  # 北東へ上る → 下りは南西
        (-0.10, 0.10, 135.0),
        (0.10, -0.10, 315.0),
        (-0.10, -0.10, 45.0),
    ],
)
def test_t030_slope_and_aspect_on_a_plane(a, b, expected_aspect):
    mpp = 7.83
    grid = plane(9, mpp, a, b)

    slope, aspect = terrain.slope_aspect(grid, mpp)

    expected_slope = math.degrees(math.atan(math.hypot(a, b)))
    assert slope == pytest.approx(expected_slope, abs=1e-9)
    assert aspect is not None
    assert aspect == pytest.approx(expected_aspect, abs=1e-9)


def test_t032_flat_ground_has_zero_slope_and_no_aspect():
    grid = plane(9, 7.83, 0.0, 0.0)
    slope, aspect = terrain.slope_aspect(grid, 7.83)
    assert slope == pytest.approx(0.0, abs=1e-12)
    assert aspect is None, "平坦地の方位は未定義。0 度(北)と区別する"


# ---------------------------------------------------------------------- T-031


def test_t031_positive_control_wrong_pixel_size_fails():
    """画素サイズを取り違えた実装は解析解に合わない。"""
    a, b, mpp = 0.10, 0.0, 7.83
    grid = plane(9, mpp, a, b)
    correct, _ = terrain.slope_aspect(grid, mpp)
    wrong, _ = terrain.slope_aspect(grid, mpp * 2)
    assert correct != pytest.approx(wrong, abs=1e-6), (
        "画素サイズを 2 倍にしても同じ傾斜が出る。この検査は撃っていない"
    )


def test_t031_positive_control_transposed_grid_changes_aspect():
    """x と y を取り違えた実装は方位が変わる。"""
    grid = plane(9, 7.83, 0.10, 0.03)
    _, aspect = terrain.slope_aspect(grid, 7.83)
    _, transposed = terrain.slope_aspect(grid.T.copy(), 7.83)
    assert aspect is not None and transposed is not None
    assert abs(aspect - transposed) > 1.0, (
        "転置しても方位が変わらない。x と y の取り違えを捕まえられない"
    )


# ---------------------------------------------------------------------- T-033


def test_t033_local_relief_is_bracketed_by_the_analytic_value():
    """円窓の起伏は `2·r·g` に挟まれる。

    連続平面なら直径の両端で厳密に `2·r·g`。画素は離散なので、いちばん遠い
    画素は `r - mpp·√2` 以上 `r` 以下の距離にある。この二つで挟む。
    """
    a, b, mpp, radius = 0.05, 0.02, 10.0, 500.0
    g = math.hypot(a, b)
    size = int(2 * radius / mpp) + 3
    size += (size + 1) % 2
    grid = plane(size, mpp, a, b)

    relief = terrain.local_relief(grid, mpp, radius)

    upper = 2 * radius * g
    lower = 2 * (radius - mpp * math.sqrt(2)) * g
    assert lower <= relief <= upper, f"{lower} <= {relief} <= {upper} が成り立たない"


def test_t033_relative_elevation_on_a_plane_is_exactly_zero():
    """円窓は中心について対称なので、平面の窓平均は中心値に一致する。"""
    a, b, mpp, radius = 0.05, -0.03, 10.0, 500.0
    size = int(2 * radius / mpp) + 3
    size += (size + 1) % 2
    grid = plane(size, mpp, a, b)

    # 前提の検算: 使うマスクが中心対称であること。
    mask = terrain.disc_mask(grid.shape, radius / mpp)
    assert np.array_equal(mask, mask[::-1, ::-1]), "円窓が中心対称でない"

    assert terrain.relative_elevation(grid, mpp, radius) == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------- T-034


def test_t034_tri_matches_the_closed_form():
    """Riley の TRI は平面上で `mpp·√6·√(a²+b²)`。

    先に 8 近傍の高度差を一つずつ検算してから閉形式を使う。
    """
    a, b, mpp = 0.07, -0.04, 7.83
    grid = plane(5, mpp, a, b)
    centre = grid[2, 2]

    # 導出の前提: 中心と各近傍の差(中心 − 近傍)。
    expected_diffs = {
        (-1, 0): -b * mpp,  # 北
        (1, 0): b * mpp,  # 南
        (0, 1): -a * mpp,  # 東
        (0, -1): a * mpp,  # 西
        (-1, 1): -(a + b) * mpp,  # 北東
        (1, -1): (a + b) * mpp,  # 南西
        (-1, -1): (a - b) * mpp,  # 北西
        (1, 1): -(a - b) * mpp,  # 南東
    }
    for (di, dj), expected in expected_diffs.items():
        got = centre - grid[2 + di, 2 + dj]
        assert got == pytest.approx(expected, abs=1e-9), f"近傍 {(di, dj)} の差"

    sum_sq = sum(v**2 for v in expected_diffs.values())
    assert sum_sq == pytest.approx(6 * mpp**2 * (a**2 + b**2), abs=1e-9)

    assert terrain.tri(grid, mpp) == pytest.approx(
        mpp * math.sqrt(6) * math.hypot(a, b), abs=1e-9
    )


# ---------------------------------------------------------------------- T-038


def test_t038_openness_proxy_on_a_plane_is_just_under_a_half():
    """平面では中心より低い画素がちょうど半分弱になる(等高の線があるぶん)。"""
    grid = plane(101, 10.0, 0.05, 0.02)
    value = terrain.openness_proxy(grid, 10.0, 500.0)
    assert 0.45 <= value <= 0.50, value


# ---------------------------------------------------------------------- T-035


def test_t035_missing_values_are_not_filled_with_zero():
    """NoData を 0 で埋めない(構想書 §14.5)。"""
    mpp = 10.0
    grid = plane(41, mpp, 0.05, 0.0)
    grid[0:5, :] = np.nan  # 窓の一部が欠測

    slope, _ = terrain.slope_aspect(grid, mpp)
    assert slope == pytest.approx(math.degrees(math.atan(0.05)), abs=1e-9), (
        "中心の 3×3 が揃っていれば傾斜は出る"
    )

    relief = terrain.local_relief(grid, mpp, 200.0)
    assert relief is not None and relief > 0

    # 0 埋めしていたら、欠測帯が『標高 0 の崖』になって起伏が跳ね上がる。
    zero_filled = np.nan_to_num(grid, nan=0.0)
    assert terrain.local_relief(zero_filled, mpp, 200.0) > relief * 2


def test_t035_all_missing_window_returns_none():
    grid = np.full((21, 21), np.nan)
    slope, aspect = terrain.slope_aspect(grid, 10.0)
    assert slope is None and aspect is None
    assert terrain.local_relief(grid, 10.0, 100.0) is None
    assert terrain.relative_elevation(grid, 10.0, 100.0) is None
    assert terrain.tri(grid, 10.0) is None
    assert terrain.openness_proxy(grid, 10.0, 100.0) is None


def test_t035_missing_ratio_is_reported():
    grid = plane(21, 10.0, 0.01, 0.0)
    grid[:, :7] = np.nan  # 21 列中 7 列
    assert terrain.missing_ratio(grid) == pytest.approx(7 / 21, abs=1e-9)


# ---------------------------------------------------------------------- T-043


def test_t043_rounding_keeps_aspect_in_the_half_open_range():
    """丸めが `[0, 360)` の外へ押し出さない。

    実データで 1 件、`round(359.9996, 2) == 360.0` が JSON Schema の
    `exclusiveMaximum` に引っかかった。丸めた**後**で確かめる。
    """
    assert round(359.9996, 2) == 360.0, "この丸めが問題を起こす前提そのもの"
    assert terrain.round_aspect(359.9996) == pytest.approx(0.0)
    assert terrain.round_aspect(359.99) == pytest.approx(359.99)
    assert terrain.round_aspect(0.0) == pytest.approx(0.0)
    assert terrain.round_aspect(180.005) == pytest.approx(180.0, abs=0.01)
    assert terrain.round_aspect(None) is None


def test_t043_every_aspect_from_a_plane_survives_rounding():
    """全方位を掃いて、丸めた後も定義域に留まることを確かめる。"""
    for degrees in range(0, 3600):
        radians = math.radians(degrees / 10)
        a, b = math.sin(radians) * 0.1, math.cos(radians) * 0.1
        _, aspect = terrain.slope_aspect(plane(5, 7.83, a, b), 7.83)
        rounded = terrain.round_aspect(aspect)
        assert rounded is not None
        assert 0.0 <= rounded < 360.0, (degrees, aspect, rounded)
