"""国土地理院 標高タイルの復号とタイル座標。

復号規則は構想書 §14.2(国土地理院「標高タイルの仕様」):

    x = 2^16 R + 2^8 G + B
    x <  2^23 : h = 0.01 x
    x == 2^23 : 標高なし(NA)
    x >  2^23 : h = 0.01 (x - 2^24)

外部形式を読むので、仮定が崩れたらその場で落ちる検算をコードの中に置く(HC-075)。
黙って違う結果を出す道を残さない。
"""

from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image

TILE_PX = 256
EARTH_CIRCUMFERENCE_M = 40_075_016.686
# Web メルカトルの赤道での 1 画素あたり地上距離(z=0, 256px タイル)。
BASE_METERS_PER_PIXEL = EARTH_CIRCUMFERENCE_M / TILE_PX

NA_RAW = 2**23
WRAP_RAW = 2**24

# 国土地理院の標高タイル(優先順は構想書 §14.3)。値は XYZ の layer 名。
DEM_LAYERS: tuple[tuple[str, int], ...] = (
    ("dem5a_png", 15),
    ("dem5b_png", 15),
    ("dem5c_png", 15),
    ("dem_png", 14),
)


def decode_tile(png_bytes: bytes) -> np.ndarray:
    """標高タイル PNG を float の配列へ復号する。NA は NaN。

    8 ビット RGB 以外は例外にする。16 ビット PNG やパレット PNG を黙って
    ``convert("RGB")`` すると、値が切り詰められたまま「もっともらしい標高」が出る。
    """
    img = Image.open(io.BytesIO(png_bytes))
    if img.mode not in {"RGB", "RGBA"}:
        raise ValueError(
            f"標高タイルは 8 ビット RGB を前提にしている(受け取ったモード: {img.mode})"
        )
    arr = np.asarray(img.convert("RGB"), dtype=np.int64)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"RGB 3 面を前提にしている(受け取った形: {arr.shape})")

    raw = (arr[..., 0] << 16) | (arr[..., 1] << 8) | arr[..., 2]
    height = np.where(raw < NA_RAW, raw, raw - WRAP_RAW).astype(np.float64) * 0.01
    height[raw == NA_RAW] = np.nan
    return height


def nanmax(grid: np.ndarray) -> float | None:
    """欠測を除いた最大値。全欠測なら None。"""
    if not np.isfinite(grid).any():
        return None
    return float(np.nanmax(grid))


def lonlat_to_tile_f(lon: float, lat: float, z: int) -> tuple[float, float]:
    """経緯度を Web メルカトルのタイル座標(小数)へ。"""
    if not -85.05113 <= lat <= 85.05113:
        raise ValueError(f"Web メルカトルの範囲外の緯度: {lat}")
    n = 2.0**z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    """経緯度を含むタイルの番号。"""
    x, y = lonlat_to_tile_f(lon, lat, z)
    return int(math.floor(x)), int(math.floor(y))


def meters_per_pixel(lat: float, z: int) -> float:
    """その緯度・ズームでの 1 画素の地上距離(m)。"""
    return BASE_METERS_PER_PIXEL * math.cos(math.radians(lat)) / (2.0**z)


def window_tiles(
    lon: float, lat: float, z: int, radius_m: float
) -> set[tuple[int, int]]:
    """点を中心とする一辺 2*radius_m の窓に重なるタイルの集合。"""
    if radius_m <= 0:
        raise ValueError("窓の半径は正でなければならない")
    half_px = radius_m / meters_per_pixel(lat, z)
    fx, fy = lonlat_to_tile_f(lon, lat, z)
    gx, gy = fx * TILE_PX, fy * TILE_PX
    x0 = int(math.floor((gx - half_px) / TILE_PX))
    x1 = int(math.floor((gx + half_px) / TILE_PX))
    y0 = int(math.floor((gy - half_px) / TILE_PX))
    y1 = int(math.floor((gy + half_px) / TILE_PX))
    return {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}


def tile_url(layer: str, z: int, x: int, y: int) -> str:
    return f"https://cyberjapandata.gsi.go.jp/xyz/{layer}/{z}/{x}/{y}.png"
