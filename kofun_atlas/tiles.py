"""標高タイルのローカルキャッシュと、窓のモザイク組み立て。

キャッシュ(`data/raw/gsi-cache/`)は**リポジトリに入れない**。
全国 DEM を丸ごと再配布しないため(構想書 §2.4)。
出荷するのは派生した特徴量だけである。

タイルがどの層にも無いことは障害ではなく「陸地が無い」という答えである
(実測 2026-09-08: 無作為 40 件の窓 160 タイル中 1 枚が該当。瀬戸内海の海域)。
その場合は NoData(NaN)として扱う。
"""

from __future__ import annotations

import json
import math
import pathlib

import numpy as np

from . import dem

TILE_PX = dem.TILE_PX
DEFAULT_ZOOM = 14
DEFAULT_RADIUS_M = 1000.0

# 層の優先順(構想書 §14.3)。z14 では dem5a がタイルの 99.4% を覆う(実測)。
LAYER_PRIORITY: tuple[str, ...] = ("dem5a_png", "dem5b_png", "dem5c_png", "dem_png")


def cache_path(root: pathlib.Path, layer: str, z: int, x: int, y: int) -> pathlib.Path:
    return root / layer / str(z) / str(x) / f"{y}.png"


def window_bounds(
    lon: float, lat: float, z: int, radius_m: float
) -> tuple[int, int, int, int, float]:
    """窓の全体画素座標 `(x0, y0, x1, y1)` と 1 画素の地上距離を返す。

    中心画素を含む奇数辺になるよう、両側に同じ画素数を取る。
    """
    mpp = dem.meters_per_pixel(lat, z)
    half = int(math.ceil(radius_m / mpp))
    fx, fy = dem.lonlat_to_tile_f(lon, lat, z)
    cx, cy = int(math.floor(fx * TILE_PX)), int(math.floor(fy * TILE_PX))
    return cx - half, cy - half, cx + half, cy + half, mpp


def tiles_for_window(
    lon: float, lat: float, z: int, radius_m: float
) -> list[tuple[int, int]]:
    x0, y0, x1, y1 = window_bounds(lon, lat, z, radius_m)[:4]
    return [
        (tx, ty)
        for tx in range(x0 // TILE_PX, x1 // TILE_PX + 1)
        for ty in range(y0 // TILE_PX, y1 // TILE_PX + 1)
    ]


class TileStore:
    """キャッシュ済みタイルを読み、層の割り当てを索引で覚える。

    **層は画素単位で合成する。** 「タイルが存在する ⇒ 値がある」は偽で、
    DEM5A はタイルがあっても大半が NoData のことがある(実測 2026-09-08:
    石馬谷古墳の中心タイルは DEM5A が 82.1% 欠測・中心画素も NaN。
    同じタイルの DEM10B は欠測 0% で 29.17 m)。
    上位層を土台に、NaN の画素だけを下位層で埋める。
    どの層にも値が無い画素は NaN のまま残す —— 水面には標高が無い。
    """

    def __init__(self, root: pathlib.Path, index_path: pathlib.Path):
        self.root = pathlib.Path(root)
        self.index_path = pathlib.Path(index_path)
        self.index: dict[str, list[str]] = {}
        if self.index_path.exists():
            for line in self.index_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.index[row["key"]] = list(row.get("layers") or [])

    @staticmethod
    def key(z: int, x: int, y: int) -> str:
        return f"{z}/{x}/{y}"

    def layers_of(self, z: int, x: int, y: int) -> list[str]:
        return self.index.get(self.key(z, x, y), [])

    def grid(self, z: int, x: int, y: int) -> np.ndarray:
        """1 タイルを標高配列で返す。層を優先順に重ねて穴を埋める。"""
        key = self.key(z, x, y)
        if key not in self.index:
            raise KeyError(f"タイル {key} が索引に無い。先に fetch_dem.py を走らせること")

        out = np.full((TILE_PX, TILE_PX), np.nan)
        for layer in self.index[key]:
            path = cache_path(self.root, layer, z, x, y)
            if not path.exists():
                raise FileNotFoundError(f"索引にはあるがファイルが無い: {path}")
            holes = np.isnan(out)
            if not holes.any():
                break
            out[holes] = dem.decode_tile(path.read_bytes())[holes]
        return out

    def window(
        self,
        lon: float,
        lat: float,
        z: int = DEFAULT_ZOOM,
        radius_m: float = DEFAULT_RADIUS_M,
    ) -> tuple[np.ndarray, float, dict[str | None, int]]:
        """窓のモザイクと 1 画素の地上距離、寄与した層の内訳を返す。"""
        x0, y0, x1, y1, mpp = window_bounds(lon, lat, z, radius_m)
        height, width = y1 - y0 + 1, x1 - x0 + 1
        out = np.full((height, width), np.nan)
        contributions: dict[str, int] = {}

        for tx in range(x0 // TILE_PX, x1 // TILE_PX + 1):
            for ty in range(y0 // TILE_PX, y1 // TILE_PX + 1):
                tile = self.grid(z, tx, ty)
                layers = self.layers_of(z, tx, ty)

                gx0, gy0 = tx * TILE_PX, ty * TILE_PX
                sx0, sx1 = max(x0, gx0), min(x1, gx0 + TILE_PX - 1)
                sy0, sy1 = max(y0, gy0), min(y1, gy0 + TILE_PX - 1)
                if sx0 > sx1 or sy0 > sy1:
                    continue
                out[sy0 - y0 : sy1 - y0 + 1, sx0 - x0 : sx1 - x0 + 1] = tile[
                    sy0 - gy0 : sy1 - gy0 + 1, sx0 - gx0 : sx1 - gx0 + 1
                ]
                for layer in layers or ["none"]:
                    contributions[layer] = contributions.get(layer, 0) + 1

        if out.shape[0] % 2 == 0 or out.shape[1] % 2 == 0:
            raise ValueError(f"窓が中心画素を持たない形になった: {out.shape}")
        return out, mpp, contributions
