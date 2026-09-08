"""標高格子から地形特徴量を出す(構想書 §14.4)。

すべて **中心画素**を対象点として計算する。欠測(NaN)は 0 で埋めない ——
0 で埋めると欠測帯が「標高 0 の崖」になり、起伏が跳ね上がる(構想書 §14.5)。

角度の約束:
- `slope_deg` は水平からの傾き(0〜90)
- `aspect_deg` は**最急降下方向**の方位角(北 0、東 90、時計回り)。
  平坦地では未定義なので `None` を返す —— 0 度(北)と混ぜない
"""

from __future__ import annotations

import math

import numpy as np

__all__ = [
    "disc_mask",
    "round_aspect",
    "local_relief",
    "missing_ratio",
    "openness_proxy",
    "relative_elevation",
    "slope_aspect",
    "tri",
]


def round_aspect(aspect: float | None, digits: int = 2) -> float | None:
    """方位角を丸めてから半開区間 `[0, 360)` へ戻す。

    **丸めは値域の外へ押し出す。** `round(359.9996, 2)` は `360.0` になり、
    「北」を表すはずの値が定義域を外れる。丸めた後に正規化しないと、
    出荷の直前(スキーマ検証)まで気づけない。
    """
    if aspect is None:
        return None
    return round(aspect, digits) % 360.0


def _centre(grid: np.ndarray) -> tuple[int, int]:
    if grid.ndim != 2:
        raise ValueError(f"2 次元の格子を前提にしている: {grid.shape}")
    if grid.shape[0] % 2 == 0 or grid.shape[1] % 2 == 0:
        raise ValueError(f"中心画素を持つ奇数辺を前提にしている: {grid.shape}")
    return grid.shape[0] // 2, grid.shape[1] // 2


def missing_ratio(grid: np.ndarray) -> float:
    return float(np.isnan(grid).mean())


def disc_mask(shape: tuple[int, int], radius_px: float) -> np.ndarray:
    """中心からの距離が `radius_px` 以下の画素を True にする。

    中心対称であること(平面の窓平均が中心値に一致するための前提)は
    `<=` 比較と中心原点から従う。
    """
    rows, cols = shape
    ci, cj = rows // 2, cols // 2
    di = np.arange(rows)[:, None] - ci
    dj = np.arange(cols)[None, :] - cj
    return (di**2 + dj**2) <= radius_px**2


def slope_aspect(
    grid: np.ndarray, mpp: float
) -> tuple[float | None, float | None]:
    """中心画素の傾斜(度)と最急降下方位(度)。Horn の 3×3 法。

    平面に対して有限差分が厳密になるので、解析解と等号で比べられる。
    """
    ci, cj = _centre(grid)
    if ci < 1 or cj < 1:
        raise ValueError("3×3 を取れる大きさが要る")
    win = grid[ci - 1 : ci + 2, cj - 1 : cj + 2]
    if np.isnan(win).any():
        return (None, None)

    # dz/dx は東向き、dz/dy は北向きに揃える(行 i は南へ増えるので符号を反転)。
    dz_dx = (
        (win[0, 2] + 2 * win[1, 2] + win[2, 2])
        - (win[0, 0] + 2 * win[1, 0] + win[2, 0])
    ) / (8 * mpp)
    dz_dy = (
        (win[0, 0] + 2 * win[0, 1] + win[0, 2])
        - (win[2, 0] + 2 * win[2, 1] + win[2, 2])
    ) / (8 * mpp)

    gradient = math.hypot(dz_dx, dz_dy)
    slope = math.degrees(math.atan(gradient))
    if gradient == 0.0:
        return (slope, None)

    # 最急降下は勾配の逆向き。方位角は北から時計回り。
    aspect = math.degrees(math.atan2(-dz_dx, -dz_dy)) % 360.0
    return (slope, aspect)


def local_relief(grid: np.ndarray, mpp: float, radius_m: float) -> float | None:
    """半径 `radius_m` の円窓内の最大標高差。"""
    mask = disc_mask(grid.shape, radius_m / mpp)
    values = grid[mask]
    values = values[~np.isnan(values)]
    if values.size == 0:
        return None
    return float(values.max() - values.min())


def relative_elevation(
    grid: np.ndarray, mpp: float, radius_m: float
) -> float | None:
    """中心標高 − 円窓の平均標高。"""
    ci, cj = _centre(grid)
    centre = grid[ci, cj]
    if np.isnan(centre):
        return None
    mask = disc_mask(grid.shape, radius_m / mpp)
    values = grid[mask]
    values = values[~np.isnan(values)]
    if values.size == 0:
        return None
    return float(centre - values.mean())


def tri(grid: np.ndarray, mpp: float) -> float | None:
    """Riley らの Terrain Ruggedness Index。

    中心と 8 近傍の高度差の二乗和の平方根。`mpp` は使わないが、
    ほかの特徴と署名を揃えて呼び違いを防ぐ。
    """
    ci, cj = _centre(grid)
    if ci < 1 or cj < 1:
        raise ValueError("3×3 を取れる大きさが要る")
    win = grid[ci - 1 : ci + 2, cj - 1 : cj + 2]
    if np.isnan(win).any():
        return None
    centre = win[1, 1]
    diffs = np.delete(win.ravel(), 4) - centre
    return float(math.sqrt(float((diffs**2).sum())))


def openness_proxy(
    grid: np.ndarray, mpp: float, radius_m: float
) -> float | None:
    """円窓のうち中心より低い画素の割合。

    **本アプリ定義の代理指標**であり、Yokoyama らの openness とは別物である。
    1 に近いほど周囲から突き出た地点、0 に近いほど窪んだ地点を意味する。
    """
    ci, cj = _centre(grid)
    centre = grid[ci, cj]
    if np.isnan(centre):
        return None
    mask = disc_mask(grid.shape, radius_m / mpp)
    values = grid[mask]
    values = values[~np.isnan(values)]
    if values.size == 0:
        return None
    return float((values < centre).sum() / values.size)
