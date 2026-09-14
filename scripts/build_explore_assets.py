"""探索画面の資産と、集計の照合表を作る(SPEC §3.14)。

    python scripts/build_explore_assets.py

出力:
  public/data/explore.json              画面が読む並び・座標・所在・地形の値
  tests/fixtures/explore-reference.json 範囲選択と集計の照合表(G-30 / G-31)

**照合表は画面の実装とは独立に作る。** numpy の分位関数は補間の流儀が選べて、
TypeScript 側と規則がずれやすい(HC-073)。ここでは SPEC §3.14 に宣言した規則を
素の Python(並べ替えと添字だけ)で書き下ろす。境界や中央値は配らない —— 画面は
配った値から TypeScript で計算し、それをこの照合表と突き合わせる。
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "kofun.json"
PROJECTION = ROOT / "public" / "data" / "projection.json"
POINTS = ROOT / "public" / "data" / "kofun-points.geojson"
OUT = ROOT / "public" / "data" / "explore.json"
FIXTURE = ROOT / "tests" / "fixtures" / "explore-reference.json"

METRICS = ("elevation_m", "slope_deg", "openness_500m")
CLASSES = 5


def median(values: list[float | None]) -> float | None:
    """値のある件を昇順に並べ、奇数個なら真ん中、偶数個なら真ん中二つの平均。"""
    v = sorted(x for x in values if x is not None)
    n = len(v)
    if n == 0:
        return None
    if n % 2 == 1:
        return v[n // 2]
    return (v[n // 2 - 1] + v[n // 2]) / 2


def quantile_breaks(values: list[float | None], k: int = CLASSES) -> list[float]:
    """第 j 境界(j = 1..k-1)は v[floor(j*n/k)]。"""
    v = sorted(x for x in values if x is not None)
    n = len(v)
    if n < k:
        return []
    return [v[math.floor(j * n / k)] for j in range(1, k)]


def class_of(value: float | None, breaks: list[float]) -> int | None:
    """境界ちょうどの値は上のクラス。値なしはクラス無し。"""
    if value is None:
        return None
    return sum(1 for b in breaks if value >= b)


def select_in_rect(xy: list[list[float]], rect: dict) -> list[int]:
    """辺ちょうどの点を含む。"""
    return [
        i
        for i, (x, y) in enumerate(xy)
        if rect["x0"] <= x <= rect["x1"] and rect["y0"] <= y <= rect["y1"]
    ]


def main() -> int:
    for path in (PROCESSED, PROJECTION, POINTS):
        if not path.exists():
            print(f"{path} が無い", file=sys.stderr)
            return 1

    records = json.loads(PROCESSED.read_text(encoding="utf-8"))
    projection = json.loads(PROJECTION.read_text(encoding="utf-8"))
    points = json.loads(POINTS.read_text(encoding="utf-8"))

    ids = projection["ids"]
    if ids != [f["properties"]["id"] for f in points["features"]]:
        raise ValueError("二次元配置と点の並びが違う")
    by_id = {r["id"]: r for r in records}
    if set(by_id) != set(ids):
        raise ValueError("レコードと二次元配置の集合が違う")

    explore = {
        "note": "並び・座標は public/data/projection.json と kofun-points.geojson に一致する(T-066)",
        "ids": ids,
        "name": [f["properties"]["name"] for f in points["features"]],
        "pref": [f["properties"]["pref"] for f in points["features"]],
        "xy": projection["xy"],
        "lonlat": [f["geometry"]["coordinates"] for f in points["features"]],
        "metrics": {m: [by_id[i]["terrain"].get(m) for i in ids] for m in METRICS},
    }
    OUT.write_text(
        json.dumps(explore, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    # --- 照合表 ---------------------------------------------------------------
    xy = explore["xy"]
    xs = sorted(p[0] for p in xy)
    ys = sorted(p[1] for p in xy)
    n = len(xy)
    # 辺を実在する点の座標に合わせる。辺ちょうどの点が無いと「辺を含むか」の違いが現れない(HC-070)。
    rects = [
        {"label": "全点", "x0": -1.0, "x1": 1.0, "y0": -1.0, "y1": 1.0},
        {"label": "点 0 個", "x0": 1.1, "x1": 1.2, "y0": 1.1, "y1": 1.2},
        {"label": "中央の帯", "x0": xs[n // 4], "x1": xs[3 * n // 4], "y0": ys[n // 3], "y1": ys[2 * n // 3]},
        {"label": "左下", "x0": xs[0], "x1": xs[n // 5], "y0": ys[0], "y1": ys[n // 5]},
        {"label": "右上", "x0": xs[4 * n // 5], "x1": xs[-1], "y0": ys[4 * n // 5], "y1": ys[-1]},
        {"label": "細い縦帯", "x0": xs[n // 2], "x1": xs[n // 2 + 40], "y0": ys[0], "y1": ys[-1]},
    ]
    for rect in rects:
        rect["ids"] = select_in_rect(xy, rect)

    prefectures = sorted({p for p in explore["pref"] if p is not None})
    by_pref = {}
    for pref in prefectures:
        members = [i for i, p in enumerate(explore["pref"]) if p == pref]
        entry = {"count": len(members)}
        for m in METRICS:
            vals = [explore["metrics"][m][i] for i in members]
            entry[m] = median(vals)
            entry[f"{m}__nonnull"] = sum(1 for v in vals if v is not None)
        by_pref[pref] = entry

    breaks = {m: quantile_breaks(explore["metrics"][m]) for m in METRICS}
    class_counts = {}
    for m in METRICS:
        counts = [0] * CLASSES
        for v in explore["metrics"][m]:
            c = class_of(v, breaks[m])
            if c is not None:
                counts[c] += 1
        class_counts[m] = counts

    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(
        json.dumps(
            {
                "note": (
                    "scripts/build_explore_assets.py が SPEC §3.14 の規則を素の Python で書き下ろして作る。"
                    "中央値: 奇数は真ん中・偶数は真ん中二つの平均。境界: v[floor(j*n/5)]。"
                    "所属: x >= b の境界の数。範囲選択: 辺ちょうどを含む。"
                ),
                "rects": rects,
                "prefecture": by_pref,
                "breaks": breaks,
                "class_counts": class_counts,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )

    on_edge = sum(
        1
        for r in rects
        for i in r["ids"]
        if xy[i][0] in (r["x0"], r["x1"]) or xy[i][1] in (r["y0"], r["y1"])
    )
    even = sum(1 for e in by_pref.values() if e["elevation_m__nonnull"] % 2 == 0)
    print(f"explore.json {n:,} 件 → {OUT.stat().st_size:,} バイト")
    print("矩形ごとの点数:", [(r["label"], len(r["ids"])) for r in rects])
    print(f"辺ちょうどの点(のべ): {on_edge} / 標高の値が偶数個の県: {even} / {len(by_pref)}")
    for m in METRICS:
        print(f"{m}: 境界 {breaks[m]} / クラスの件数 {class_counts[m]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
