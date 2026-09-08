"""T-037: 同じ地点を z14 と z15 で測って食い違わないことを確かめる。

外部ネットワークに触れるので既定では走らない。
`KOFUN_ALLOW_NETWORK=1` を立てたときだけ実行する。

これは**内部整合の検査**であって外部権威との照合ではない。
解像度を変えても同じ地点の標高が動かないことしか言わない ——
復号そのものの正しさは T-009(富士山剣ヶ峰 3776.12 m)が受け持つ。
"""

from __future__ import annotations

import io
import json
import os
import random
import statistics
import urllib.error
import urllib.request

import pytest

from kofun_atlas import dem, tiles

pytestmark = pytest.mark.integration

SAMPLE_SIZE = 40
SEED = 20260908
MEDIAN_TOLERANCE_M = 1.0
USER_AGENT = "KofunAtlasAI/1.0 (research prototype)"


def _elevation_at(lon: float, lat: float, z: int) -> float | None:
    fx, fy = dem.lonlat_to_tile_f(lon, lat, z)
    tx, ty = int(fx), int(fy)
    px, py = int((fx - tx) * 256), int((fy - ty) * 256)
    for layer in tiles.LAYER_PRIORITY:
        url = dem.tile_url(layer, z, tx, ty)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=30) as resp:
                grid = dem.decode_tile(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            raise
        value = grid[py, px]
        return None if value != value else float(value)
    return None


@pytest.mark.skipif(
    not os.environ.get("KOFUN_ALLOW_NETWORK"),
    reason="KOFUN_ALLOW_NETWORK=1 のときだけ実行する",
)
def test_t037_z14_and_z15_agree(processed_path):
    records = json.loads(processed_path.read_text(encoding="utf-8"))
    random.seed(SEED)
    sample = random.sample(records, SAMPLE_SIZE)

    diffs = []
    for rec in sample:
        lon, lat = rec["location"]["lon"], rec["location"]["lat"]
        a = _elevation_at(lon, lat, 14)
        b = _elevation_at(lon, lat, 15)
        if a is None or b is None:
            continue
        diffs.append(abs(a - b))

    assert len(diffs) >= SAMPLE_SIZE // 2, f"比べられた地点が少なすぎる: {len(diffs)}"
    median = statistics.median(diffs)
    assert median <= MEDIAN_TOLERANCE_M, (
        f"z14 と z15 の中心標高の差の中央値 {median:.2f} m "
        f"(標本 {len(diffs)} 件・最大 {max(diffs):.2f} m)"
    )
