"""埋め込みの入力になる特徴行列を作る(SPEC §3.7 / §3.8)。

**V1.0 の入力は「その古墳が置かれた場所」だけである。** 墳形・墳丘長・時期・
出土品は公開スナップショットが置かれるまで 0% しか埋まらない(実測 2026-09-09)。
だからここで作るのは立地の特徴であって、古墳の総合特徴ではない。

都道府県は**入れない**。入れると「同じ地域だから似ている」を学ぶモデルになる
(構想書 §19.3 の意図)。地域は絞り込みの条件として別に置く。

欠測は 0 で埋めない。学習データの中央値で補い、同時に `is_missing` を立てる
(構想書 §19.2)。0 埋めは「その値が 0 である」という別の主張になる。
"""

from __future__ import annotations

import dataclasses
import json
import math
import pathlib
import re
from typing import Any, Iterable, Sequence

import numpy as np

EARTH_RADIUS_M = 6_371_008.8

# 「同じ代表点」とみなす距離。Geoshape の座標は小数 6 桁(緯度で約 0.1 m)なので、
# 1 m 未満は同一点の記録揺れと見てよい。実測では 0 m ちょうどか 100 m 超に分かれ、
# その間(1〜100 m)は 0 件だったので、この閾値は境界に敏感でない(2026-09-10)。
COINCIDENT_TOLERANCE_M = 1.0

# 名称が「群」を含むか。実測 2026-09-09: 2,805 件中 992 件(35.4%)。
_GROUP_RE = re.compile(r"群")

# 列の順序は**固定**である。ONNX の入力順と一致していなければならない。
FEATURE_NAMES: tuple[str, ...] = (
    "elevation_m",
    "slope_deg",
    "aspect_sin",
    "aspect_cos",
    "local_relief_250m",
    "local_relief_500m",
    "local_relief_1000m",
    "relative_elevation_500m",
    "tri",
    "openness_500m",
    "log_nearest_kofun_m",
    "kofun_within_1km",
    "kofun_within_5km",
    "shares_coordinates",
    "is_group",
    "aspect_is_missing",
    "terrain_is_missing",
)

# 循環量なので sin/cos で入れる列(欠測マスクは別に 1 本だけ立てる)。
_ASPECT_COLUMNS = ("aspect_sin", "aspect_cos")


@dataclasses.dataclass(frozen=True)
class ScalerParams:
    """中央値と IQR による標準化(構想書 §19.1)。

    墳丘長のような外れ値の大きい量に備えて標準偏差ではなく IQR を使う。
    IQR が 0 の列は 1 として扱う —— 0 で割らないため。
    """

    names: tuple[str, ...]
    median: tuple[float, ...]
    iqr: tuple[float, ...]

    def transform(self, matrix: np.ndarray) -> np.ndarray:
        if matrix.shape[1] != len(self.names):
            raise ValueError(
                f"列数が合わない: {matrix.shape[1]} != {len(self.names)}"
            )
        return (matrix - np.asarray(self.median)) / np.asarray(self.iqr)

    def to_dict(self) -> dict[str, Any]:
        return {
            "names": list(self.names),
            "median": list(self.median),
            "iqr": list(self.iqr),
        }

    @classmethod
    def fit(cls, matrix: np.ndarray, names: Sequence[str]) -> "ScalerParams":
        median = np.median(matrix, axis=0)
        q1, q3 = np.percentile(matrix, [25, 75], axis=0)
        iqr = q3 - q1
        iqr[iqr == 0] = 1.0
        return cls(tuple(names), tuple(median.tolist()), tuple(iqr.tolist()))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ScalerParams":
        return cls(
            tuple(payload["names"]),
            tuple(payload["median"]),
            tuple(payload["iqr"]),
        )


def spatial_context(records: Sequence[dict]) -> list[dict[str, float]]:
    """座標だけから出せる空間文脈。新しい出典を要らない。

    **「同じ代表点に記録された別レコード」と「空間的に近い古墳」を混ぜない。**
    Geoshape は古墳群にひとつの代表点を与えるので、座標がまったく同じ
    レコードが 181 件(80 組・実測 2026-09-10)ある。これを最近傍距離 0 m と
    して入れると `log1p(0) = 0` の縮退した山ができ、クラスタリングが
    「立地の型」ではなく**記録の重なり**を拾う。

    そこで最近傍距離は**異なる代表点まで**の距離とし、座標の共有は
    `shares_coordinates` という別の二値で明示する。
    半径内の数は「同じ点にある別レコード」も数える —— そこは
    「近くにいくつ記録があるか」を測っているので混ざらない。
    """
    lat = np.array([r["location"]["lat"] for r in records], dtype=float)
    lon = np.array([r["location"]["lon"] for r in records], dtype=float)
    y = np.radians(lat) * EARTH_RADIUS_M
    x = np.radians(lon) * EARTH_RADIUS_M * math.cos(math.radians(float(lat.mean())))

    dist = np.hypot(x[:, None] - x[None, :], y[:, None] - y[None, :])
    np.fill_diagonal(dist, np.inf)

    # 同じ代表点にある相手は「最近傍」から外す(数からは外さない)。
    coincident = dist <= COINCIDENT_TOLERANCE_M
    shares = coincident.any(axis=1)
    distinct = np.where(coincident, np.inf, dist)

    nearest = distinct.min(axis=1)
    within_1km = (dist <= 1000.0).sum(axis=1)
    within_5km = (dist <= 5000.0).sum(axis=1)
    return [
        {
            "nearest_kofun_m": float(n),
            "kofun_within_1km": float(a),
            "kofun_within_5km": float(b),
            "shares_coordinates": 1.0 if s else 0.0,
        }
        for n, a, b, s in zip(nearest, within_1km, within_5km, shares, strict=True)
    ]


def _raw_row(record: dict, context: dict[str, float]) -> dict[str, float]:
    terrain = record.get("terrain") or {}
    aspect = terrain.get("aspect_deg")
    elevation = terrain.get("elevation_m")

    row: dict[str, float] = {
        "elevation_m": elevation,
        "slope_deg": terrain.get("slope_deg"),
        "aspect_sin": None if aspect is None else math.sin(math.radians(aspect)),
        "aspect_cos": None if aspect is None else math.cos(math.radians(aspect)),
        "local_relief_250m": terrain.get("local_relief_250m"),
        "local_relief_500m": terrain.get("local_relief_500m"),
        "local_relief_1000m": terrain.get("local_relief_1000m"),
        "relative_elevation_500m": terrain.get("relative_elevation_500m"),
        "tri": terrain.get("tri"),
        "openness_500m": terrain.get("openness_500m"),
        "log_nearest_kofun_m": math.log1p(context["nearest_kofun_m"])
        if math.isfinite(context["nearest_kofun_m"])
        else None,
        "kofun_within_1km": context["kofun_within_1km"],
        "kofun_within_5km": context["kofun_within_5km"],
        "shares_coordinates": context["shares_coordinates"],
        "is_group": 1.0 if _GROUP_RE.search(record["name"]) else 0.0,
        "aspect_is_missing": 1.0 if aspect is None else 0.0,
        "terrain_is_missing": 1.0 if elevation is None else 0.0,
    }
    return row


def build_matrix(
    records: Sequence[dict],
) -> tuple[np.ndarray, np.ndarray, tuple[str, ...]]:
    """生の特徴行列と欠測マスクを返す。欠測はこの段階では NaN のまま。"""
    context = spatial_context(records)
    rows = []
    for record, ctx in zip(records, context, strict=True):
        raw = _raw_row(record, ctx)
        rows.append([np.nan if raw[name] is None else float(raw[name]) for name in FEATURE_NAMES])
    matrix = np.asarray(rows, dtype=float)
    return matrix, np.isnan(matrix), FEATURE_NAMES


def impute(matrix: np.ndarray, medians: Sequence[float] | None = None) -> tuple[np.ndarray, np.ndarray]:
    """欠測を中央値で補う。0 で埋めない(構想書 §19.2)。

    補完に使った中央値も返す —— 推論時に同じ値を使うため。
    """
    filled = matrix.copy()
    if medians is None:
        with np.errstate(all="ignore"):
            medians_arr = np.nanmedian(filled, axis=0)
        medians_arr = np.where(np.isnan(medians_arr), 0.0, medians_arr)
    else:
        medians_arr = np.asarray(medians, dtype=float)
    indices = np.where(np.isnan(filled))
    filled[indices] = np.take(medians_arr, indices[1])
    return filled, medians_arr


def load_records(path: pathlib.Path) -> list[dict]:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def top_neighbours(embedding: np.ndarray, k: int) -> np.ndarray:
    """余弦類似度の上位 k 件の索引(自分自身を除く)。"""
    norms = np.linalg.norm(embedding, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = embedding / norms
    similarity = unit @ unit.T
    np.fill_diagonal(similarity, -np.inf)
    return np.argsort(-similarity, axis=1)[:, :k]


def mean_jaccard(a: np.ndarray, b: np.ndarray) -> float:
    """行ごとの近傍集合の Jaccard 重なりの平均。"""
    if a.shape != b.shape:
        raise ValueError(f"形が違う: {a.shape} != {b.shape}")
    scores = []
    for left, right in zip(a, b, strict=True):
        sl, sr = set(left.tolist()), set(right.tolist())
        scores.append(len(sl & sr) / len(sl | sr))
    return float(np.mean(scores))


def as_iterable(value: Iterable) -> list:
    return list(value)
