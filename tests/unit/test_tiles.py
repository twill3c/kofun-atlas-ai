"""T-039 / T-040: 窓のモザイク結合。

期待値の出所: **閉形式**。全体画素座標の平面
`h = α·(gx - gx0) + β·(gy - gy0) + γ` をタイルへ焼き込み、
組み立てた窓が同じ式と厳密に一致することを求める。
1 画素のずれ・行と列の入れ替え・タイル境界の重複は、どれもこの一致を壊す。

基準点 `(gx0, gy0)` は**タイル 1 枚の原点**に取る。標高タイルは
0.01 m 刻みで ±83,886 m しか表せないので、全体画素座標(数百万)を
そのまま傾きに掛けると 24 ビット表現をはみ出す。基準点を引くのは
表現範囲に収めるためであり、位置合わせの検査は損なわれない ——
1 画素ずれれば値は `α = 0.13 m` 動き、許容差 0.005 m を大きく超える。

タイルは `dem.decode_tile` の逆(RGB へ整数を詰める)で作る。
算出器を使わずに作るので恒等式にならない(HC-045)。
"""

from __future__ import annotations

import io
import json
import math

import numpy as np
import pytest
from PIL import Image

from kofun_atlas import dem, tiles

pytestmark = pytest.mark.unit

Z = 14
ALPHA, BETA, GAMMA = 0.13, -0.07, 500.0
LON, LAT = 135.8412, 34.5394  # 箸墓古墳付近


def expected_height(gx, gy, origin):
    gx0, gy0 = origin
    return ALPHA * (gx - gx0) + BETA * (gy - gy0) + GAMMA


def _encode(values: np.ndarray) -> bytes:
    """標高(m)を国土地理院の標高タイル規則で PNG に詰める。"""
    raw = np.rint(values * 100).astype(np.int64)
    assert (np.abs(raw) < 2**23).all(), "24 ビット表現に収まる標高で作る"
    raw = raw % (2**24)
    img = Image.fromarray(
        np.stack([(raw >> 16) & 0xFF, (raw >> 8) & 0xFF, raw & 0xFF], axis=-1).astype(
            np.uint8
        ),
        mode="RGB",
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def store(tmp_path):
    needed = tiles.tiles_for_window(LON, LAT, Z, tiles.DEFAULT_RADIUS_M)
    assert len(needed) > 1, "境界をまたぐ窓でないと結合を検査できない"
    origin = (needed[0][0] * tiles.TILE_PX, needed[0][1] * tiles.TILE_PX)
    # わざと 1 枚だけ「どの層にも無い」ことにして、NaN の板が入るのを確かめる。
    absent = needed[-1]

    index_path = tmp_path / "index.jsonl"
    with index_path.open("w", encoding="utf-8", newline="\n") as fh:
        for tx, ty in needed:
            key = tiles.TileStore.key(Z, tx, ty)
            if (tx, ty) == absent:
                fh.write(json.dumps({"key": key, "layers": []}) + "\n")
                continue
            gx = tx * tiles.TILE_PX + np.arange(tiles.TILE_PX)[None, :]
            gy = ty * tiles.TILE_PX + np.arange(tiles.TILE_PX)[:, None]
            path = tiles.cache_path(tmp_path, "dem5a_png", Z, tx, ty)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_encode(expected_height(gx, gy, origin)))
            fh.write(json.dumps({"key": key, "layers": ["dem5a_png"]}) + "\n")

    return tiles.TileStore(tmp_path, index_path), origin, absent


def test_t039_mosaic_matches_the_analytic_plane(store):
    tile_store, origin, absent = store
    grid, mpp, contributions = tile_store.window(LON, LAT, Z, tiles.DEFAULT_RADIUS_M)

    x0, y0 = tiles.window_bounds(LON, LAT, Z, tiles.DEFAULT_RADIUS_M)[:2]
    gx = x0 + np.arange(grid.shape[1])[None, :]
    gy = y0 + np.arange(grid.shape[0])[:, None]
    expected = expected_height(gx, gy, origin)

    finite = ~np.isnan(grid)
    assert finite.any(), "全部欠測になっている"
    np.testing.assert_allclose(grid[finite], expected[finite], atol=0.005)

    assert np.isnan(grid).any(), "どの層にも無いタイルが NaN として入っていない"
    assert contributions.get("none") == 1
    assert mpp == pytest.approx(dem.meters_per_pixel(LAT, Z))


def test_t039_positive_control_shifted_expectation_fails(store):
    """1 画素ずらした期待値とは一致しない(= この検査は位置を見ている)。"""
    tile_store, origin, _ = store
    grid, _, _ = tile_store.window(LON, LAT, Z, tiles.DEFAULT_RADIUS_M)

    x0, y0 = tiles.window_bounds(LON, LAT, Z, tiles.DEFAULT_RADIUS_M)[:2]
    gx = x0 + 1 + np.arange(grid.shape[1])[None, :]
    gy = y0 + np.arange(grid.shape[0])[:, None]
    shifted = expected_height(gx, gy, origin)

    finite = ~np.isnan(grid)
    assert not np.allclose(grid[finite], shifted[finite], atol=0.005), (
        "1 画素ずらしても一致してしまう。位置合わせを検査できていない"
    )


def test_t039_positive_control_transposed_expectation_fails(store):
    """行と列を入れ替えた期待値とも一致しない。"""
    tile_store, origin, _ = store
    grid, _, _ = tile_store.window(LON, LAT, Z, tiles.DEFAULT_RADIUS_M)

    x0, y0 = tiles.window_bounds(LON, LAT, Z, tiles.DEFAULT_RADIUS_M)[:2]
    # gx と gy の役割を入れ替える。
    gx = x0 + np.arange(grid.shape[1])[:, None]
    gy = y0 + np.arange(grid.shape[0])[None, :]
    swapped = expected_height(gx, gy, origin)

    finite = ~np.isnan(grid)
    assert not np.allclose(grid[finite], swapped[finite], atol=0.005)


def test_t040_window_is_odd_and_covers_the_radius(store):
    tile_store, _, _ = store
    grid, mpp, _ = tile_store.window(LON, LAT, Z, tiles.DEFAULT_RADIUS_M)

    assert grid.shape[0] % 2 == 1 and grid.shape[1] % 2 == 1
    assert grid.shape[0] == grid.shape[1]
    assert grid.shape[0] // 2 == math.ceil(tiles.DEFAULT_RADIUS_M / mpp)


def test_t040_centre_pixel_is_the_one_containing_the_point():
    x0, y0, x1, y1, _ = tiles.window_bounds(LON, LAT, Z, tiles.DEFAULT_RADIUS_M)
    fx, fy = dem.lonlat_to_tile_f(LON, LAT, Z)
    assert (x0 + x1) // 2 == int(fx * tiles.TILE_PX)
    assert (y0 + y1) // 2 == int(fy * tiles.TILE_PX)


# --------------------------------------------------------------- T-041 / T-042


def _write_layer(root, layer, z, tx, ty, values):
    path = tiles.cache_path(root, layer, z, tx, ty)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_encode_with_holes(values))


def _encode_with_holes(values: np.ndarray) -> bytes:
    """NaN を国土地理院の NoData(x = 2^23)として詰める。"""
    raw = np.where(np.isnan(values), 2**23, np.rint(np.nan_to_num(values) * 100))
    raw = raw.astype(np.int64) % (2**24)
    img = Image.fromarray(
        np.stack([(raw >> 16) & 0xFF, (raw >> 8) & 0xFF, raw & 0xFF], axis=-1).astype(
            np.uint8
        ),
        mode="RGB",
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def layered_store(tmp_path):
    """上位層に穴が開き、下位層がその一部を埋める 1 枚のタイル。"""
    z, tx, ty = Z, 100, 200
    top = np.full((tiles.TILE_PX, tiles.TILE_PX), 300.0)
    top[0:64, :] = np.nan  # 上位層の穴
    bottom = np.full((tiles.TILE_PX, tiles.TILE_PX), 111.0)
    bottom[0:16, :] = np.nan  # 下位層でも埋まらない部分(水域を模す)

    _write_layer(tmp_path, "dem5a_png", z, tx, ty, top)
    _write_layer(tmp_path, "dem_png", z, tx, ty, bottom)

    index = tmp_path / "index.jsonl"
    index.write_text(
        json.dumps(
            {"key": tiles.TileStore.key(z, tx, ty), "layers": ["dem5a_png", "dem_png"]}
        )
        + "\n",
        encoding="utf-8",
    )
    return tiles.TileStore(tmp_path, index), (z, tx, ty)


def test_t041_lower_layer_fills_holes_in_the_upper_layer(layered_store):
    store, (z, tx, ty) = layered_store
    grid = store.grid(z, tx, ty)

    # 上位層に値がある部分は上位層の値のまま。
    assert grid[100, 0] == pytest.approx(300.0)
    # 上位層の穴のうち下位層に値がある部分は埋まる。
    assert grid[32, 0] == pytest.approx(111.0)
    # どちらにも無い部分は NaN のまま(水域を 0 で埋めない)。
    assert np.isnan(grid[0, 0])
    assert np.isnan(grid[:16, :]).all()
    assert not np.isnan(grid[16:, :]).any()


def test_t042_positive_control_upper_layer_alone_still_has_holes(layered_store):
    """上位層だけでは穴が残る(= T-041 は合成を見ている)。"""
    store, (z, tx, ty) = layered_store
    only_top = dem.decode_tile(
        tiles.cache_path(store.root, "dem5a_png", z, tx, ty).read_bytes()
    )
    assert np.isnan(only_top[:64, :]).all()
    assert np.isnan(only_top).mean() > np.isnan(store.grid(z, tx, ty)).mean()


def test_t042_positive_control_priority_is_respected(layered_store):
    """上位層に値がある画素を下位層が上書きしない。"""
    store, (z, tx, ty) = layered_store
    grid = store.grid(z, tx, ty)
    filled = grid[64:, :]
    assert (filled == 300.0).all(), "下位層(111.0)が上位層を上書きしている"
