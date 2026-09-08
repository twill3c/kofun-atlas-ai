"""古墳の周囲の標高タイルを取得してローカルにキャッシュする。

    python scripts/fetch_dem.py              # 未取得のタイルだけ(再開可能)
    python scripts/fetch_dem.py --limit 40   # 試し取り

キャッシュ `data/raw/gsi-cache/` は **リポジトリに入れない**(構想書 §2.4)。
出荷するのは `scripts/terrain_features.py` が作る派生特徴量だけである。

HC-221: キャッシュして再開可能にし、間を空けた再試行を入れ、
「無い」という答え(404)は再試行しない。タイルがどの層にも無いのは
「陸地が無い」という答えなので、索引に空の層リストとして記録する。

**層は画素単位で重ねる。** 「タイルが存在する ⇒ 値がある」は偽で、
DEM5A はタイルがあっても大半が NoData のことがある。最初に見つかった層で
打ち切らず、穴が残っている間だけ下位層も取る。
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from kofun_atlas import tiles  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "kofun.json"
CACHE = ROOT / "data" / "raw" / "gsi-cache"
INDEX = CACHE / "index.jsonl"

USER_AGENT = "KofunAtlasAI/1.0 (research prototype; https://github.com/)"
WORKERS = 4
TIMEOUT_S = 30
MAX_ATTEMPTS = 4
BACKOFF_S = (2, 6, 15)


def _get(url: str) -> bytes | None:
    """取得する。404 は「無い」という答えなので None を返し、再試行しない。"""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            last = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(BACKOFF_S[attempt])
    raise RuntimeError(f"{url} の取得に {MAX_ATTEMPTS} 回失敗した: {last}")


def fetch_tile(item: tuple[int, int, int]) -> dict:
    """層を優先順に試し、**穴が残っている間だけ**下位層も取る。

    「タイルが存在する ⇒ 値がある」は偽である(実測 2026-09-08:
    DEM5A はタイルがあっても 82.1% が NoData のことがある)。
    最初に見つかった層で打ち切らず、NaN が消えるまで重ねる。
    どの層にも値が無い画素は残してよい —— 水面には標高が無い。
    """
    z, x, y = item
    used: list[str] = []
    composed: np.ndarray | None = None

    for layer in tiles.LAYER_PRIORITY:
        path = tiles.cache_path(CACHE, layer, z, x, y)
        if path.exists():
            body = path.read_bytes()
        else:
            body = _get(tiles.dem.tile_url(layer, z, x, y))
            if body is None:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)

        grid = tiles.dem.decode_tile(body)
        if composed is None:
            composed = grid
        else:
            holes = np.isnan(composed)
            composed[holes] = grid[holes]
        used.append(layer)

        if not np.isnan(composed).any():
            break

    ratio = 1.0 if composed is None else float(np.isnan(composed).mean())
    return {
        "key": tiles.TileStore.key(z, x, y),
        "layers": used,
        "missing_ratio": round(ratio, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--zoom", type=int, default=tiles.DEFAULT_ZOOM)
    parser.add_argument("--radius", type=float, default=tiles.DEFAULT_RADIUS_M)
    args = parser.parse_args()

    if not PROCESSED.exists():
        print(f"{PROCESSED} が無い。先に scripts/geocode_records.py を実行すること",
              file=sys.stderr)
        return 1

    records = json.loads(PROCESSED.read_text(encoding="utf-8"))
    wanted: set[tuple[int, int, int]] = set()
    for rec in records:
        lon, lat = rec["location"]["lon"], rec["location"]["lat"]
        for tx, ty in tiles.tiles_for_window(lon, lat, args.zoom, args.radius):
            wanted.add((args.zoom, tx, ty))

    store = tiles.TileStore(CACHE, INDEX)
    todo = sorted(t for t in wanted if tiles.TileStore.key(*t) not in store.index)
    if args.limit is not None:
        todo = todo[: args.limit]

    print(
        f"z={args.zoom} 半径 {args.radius:.0f} m / 必要タイル {len(wanted):,} 枚 "
        f"/ 取得済み {len(store.index):,} / これから {len(todo):,}",
        flush=True,
    )

    CACHE.mkdir(parents=True, exist_ok=True)
    written = 0
    started = time.monotonic()
    with INDEX.open("a", encoding="utf-8", newline="\n") as fh:
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for row in pool.map(fetch_tile, todo):
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                written += 1
                if written % 200 == 0:
                    fh.flush()
                    rate = written / (time.monotonic() - started)
                    print(
                        f"  {written:,}/{len(todo):,}  {rate:.2f} 枚/秒  "
                        f"残り {(len(todo) - written) / rate / 60:.1f} 分",
                        flush=True,
                    )

    store = tiles.TileStore(CACHE, INDEX)
    by_layer: dict[str, int] = {}
    composed = 0
    for layers in store.index.values():
        if not layers:
            by_layer["どの層にも無い(陸地なし)"] = (
                by_layer.get("どの層にも無い(陸地なし)", 0) + 1
            )
            continue
        if len(layers) > 1:
            composed += 1
        for layer in layers:
            by_layer[layer] = by_layer.get(layer, 0) + 1
    print(f"追記 {written:,} 枚 / 索引 {len(store.index):,} 枚")
    print(f"二層以上を重ねたタイル: {composed:,} 枚")
    for layer, count in sorted(by_layer.items(), key=lambda kv: -kv[1]):
        print(f"  {layer}: {count:,} 枚 ({count / len(store.index):.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
