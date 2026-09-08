"""T-009〜T-013: 標高タイルの復号とタイル座標。

期待値の出所:
- T-009 / T-011: **外部権威**。国土地理院が公表する富士山剣ヶ峰の標高 3776.12 m
  (最高地点。二等三角点「富士山」は 3775.51 m)。
  復号側の計算を一切使っていないので循環しない(HC-045)。
- T-010: 構想書 §14.2 の符号規則から直接構成した合成値。実装から作らない。
- T-012: 閉形式(z=0 の中心は必ずタイル (0,0) の中心)と、2026-09-08 に実測した
  富士山頂を含む z15 タイル番号。
"""

from __future__ import annotations

import io
import math

import pytest
from PIL import Image

from kofun_atlas import dem

pytestmark = pytest.mark.unit

# 国土地理院が公表する富士山剣ヶ峰の標高(最高地点)。
FUJI_SUMMIT_M = 3776.12
# SPEC G-06 の許容差。
FUJI_TOLERANCE_M = 2.0
FIXTURE_TILE = "dem5a_15_29011_12939.png"


def _synthetic_tile(values: list[int]) -> bytes:
    """与えた整数 x をそのまま R,G,B へ詰めた 1 行 PNG を作る。

    x = 65536*R + 256*G + B(構想書 §14.2)。復号器を使わずに構成する。
    """
    img = Image.new("RGB", (len(values), 1))
    for i, x in enumerate(values):
        assert 0 <= x < 2**24, "24 ビットに収まる値だけを置く"
        img.putpixel((i, 0), ((x >> 16) & 0xFF, (x >> 8) & 0xFF, x & 0xFF))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_t009_fuji_summit_is_recovered(fixtures_dir):
    """T-009 / G-06: 復号した最大標高が公表値と ±2 m 以内で一致する。"""
    tile = fixtures_dir / FIXTURE_TILE
    grid = dem.decode_tile(tile.read_bytes())
    assert grid.shape == (256, 256)

    observed = dem.nanmax(grid)
    assert observed is not None, "フィクスチャタイルが全欠測ではないこと"
    assert abs(observed - FUJI_SUMMIT_M) <= FUJI_TOLERANCE_M, (
        f"復号最大 {observed:.2f} m が公表値 {FUJI_SUMMIT_M} m から "
        f"{abs(observed - FUJI_SUMMIT_M):.2f} m 離れている"
    )


def test_t011_positive_control_rb_swapped_decoder_fails(fixtures_dir):
    """T-011: R と B を入れ替えた復号はこのオラクルに落ちる。

    落ちなければ T-009 は何も検査していない。
    """
    tile = fixtures_dir / FIXTURE_TILE
    img = Image.open(io.BytesIO(tile.read_bytes())).convert("RGB")
    r, g, b = img.split()
    swapped = io.BytesIO()
    Image.merge("RGB", (b, g, r)).save(swapped, format="PNG")

    grid = dem.decode_tile(swapped.getvalue())
    observed = dem.nanmax(grid)
    assert observed is None or abs(observed - FUJI_SUMMIT_M) > FUJI_TOLERANCE_M, (
        "R/B を入れ替えても公表値に一致してしまう。このオラクルは撃っていない"
    )


def test_t010_sign_and_na_branches():
    """T-010: 正・NA・負の三分岐(構想書 §14.2)。"""
    values = [0, 1, 12_345, 2**23 - 1, 2**23, 2**23 + 1, 2**24 - 1]
    grid = dem.decode_tile(_synthetic_tile(values))
    row = grid[0]

    assert row[0] == pytest.approx(0.0)
    assert row[1] == pytest.approx(0.01)
    assert row[2] == pytest.approx(123.45)
    assert row[3] == pytest.approx((2**23 - 1) * 0.01)
    assert math.isnan(row[4]), "x == 2^23 は NA"
    assert row[5] == pytest.approx((2**23 + 1 - 2**24) * 0.01)
    assert row[6] == pytest.approx(-0.01)


def test_t012_lonlat_to_tile_known_values():
    """T-012: 閉形式と実測タイル番号。"""
    # z=0 は世界が 1 枚。経度 0・緯度 0 はタイル (0,0) の中心。
    x, y = dem.lonlat_to_tile_f(0.0, 0.0, 0)
    assert x == pytest.approx(0.5)
    assert y == pytest.approx(0.5)

    # z=1 で東経 90 度・北緯 0 度は右半分の左端(x=1.5 の左, つまり x=1.5)
    x, y = dem.lonlat_to_tile_f(90.0, 0.0, 1)
    assert x == pytest.approx(1.5)
    assert y == pytest.approx(1.0)

    # 2026-09-08 実測: 富士山剣ヶ峰(35.360833, 138.7275)を含む z15 タイル。
    assert dem.lonlat_to_tile(138.7275, 35.360833, 15) == (29011, 12939)


def test_t013_window_tiles_cover_corners_and_nothing_else():
    """T-013: ±1000 m 窓のタイル集合が四隅を含み、窓外を含まない。"""
    lon, lat, z, radius = 135.8412, 34.5394, 14, 1000.0  # 箸墓古墳付近
    tiles = dem.window_tiles(lon, lat, z, radius)

    mpp = dem.meters_per_pixel(lat, z)
    half_px = radius / mpp
    gx, gy = (v * 256 for v in dem.lonlat_to_tile_f(lon, lat, z))

    corners = {
        (int((gx + sx * half_px) // 256), int((gy + sy * half_px) // 256))
        for sx in (-1, 1)
        for sy in (-1, 1)
    }
    assert corners <= tiles, "窓の四隅を含むタイルが欠けている"

    x0, x1 = (gx - half_px) // 256, (gx + half_px) // 256
    y0, y1 = (gy - half_px) // 256, (gy + half_px) // 256
    for tx, ty in tiles:
        assert x0 <= tx <= x1 and y0 <= ty <= y1, f"窓外のタイル {(tx, ty)} を含む"
