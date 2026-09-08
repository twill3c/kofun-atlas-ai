"""座標から都道府県・市区町村を決める(SPEC §3.2)。

Geoshape の `都道府県コード` と `住所` の県名はどちらも行ごとに誤るので使わない。
国土地理院の逆ジオコーダが返す `muniCd` を正本にし、名称は同じ国土地理院の
市区町村表(`maps.gsi.go.jp/js/muni.js`)で引く。

逆ジオコーダの `{}` は**障害ではなく「陸上でない」という答え**である。
404 と同じく再試行してはならない(HC-221)。
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import re
from typing import Any

REVGEO_URL = "https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress"
MUNI_URL = "https://maps.gsi.go.jp/js/muni.js"
SOURCE_ID = "gsi_revgeo"

# 逆ジオコーダの座標は 6 桁で送る。鍵もそれに合わせる。
COORD_DIGITS = 6

_MUNI_LINE = re.compile(
    r'GSI\.MUNI_ARRAY\["(?P<key>\d+)"\]\s*=\s*\'(?P<body>[^\']*)\''
)
# 政令市の区名は全角空白で区切られている(例: 札幌市　中央区)。
_FULLWIDTH_SPACE = "　"


@dataclasses.dataclass(frozen=True)
class MuniEntry:
    pref_code: str
    pref_name: str
    muni_cd: str
    muni_name: str


def _normalise_code(code: str | int) -> str:
    """`01217` と `1217` を同じ鍵にする。"""
    return str(int(str(code)))


def load_muni_table(path: pathlib.Path) -> dict[str, MuniEntry]:
    """国土地理院の市区町村表を読む。

    行の形が変わったら黙って空を返さず落ちる(HC-075)。
    """
    text = pathlib.Path(path).read_text(encoding="utf-8")
    table: dict[str, MuniEntry] = {}
    for match in _MUNI_LINE.finditer(text):
        body = match.group("body")
        if not body:
            # 表には値が空の行がある(廃止された団体)。飛ばしてよい。
            continue
        fields = body.split(",")
        if len(fields) != 4:
            raise ValueError(
                f"市区町村表の行が 4 欄でない: {match.group(0)[:80]!r}"
            )
        pref_code, pref_name, muni_cd, muni_name = fields
        table[_normalise_code(match.group("key"))] = MuniEntry(
            pref_code=pref_code.strip(),
            pref_name=pref_name.strip(),
            muni_cd=muni_cd.strip().zfill(5),
            muni_name=muni_name.strip().replace(_FULLWIDTH_SPACE, " "),
        )
    if not table:
        raise ValueError(f"{path} から市区町村を 1 件も読めなかった")
    return table


def lookup_muni(code: str | int | None, table: dict[str, MuniEntry]) -> MuniEntry | None:
    if code is None:
        return None
    try:
        key = _normalise_code(code)
    except ValueError:
        return None
    return table.get(key)


def parse_response(payload: Any) -> tuple[str | None, str | None]:
    """逆ジオコーダの応答を `(muniCd, lv01Nm)` にする。

    - 陸上: `{"results": {"muniCd": "01217", "lv01Nm": "工栄町"}}`
    - 陸上でない: `{}`(または `{"results": {}}`)→ `(None, None)`
    - それ以外の形: 例外(黙って None にしない)
    """
    if not isinstance(payload, dict):
        raise ValueError(f"逆ジオコーダの応答が辞書でない: {type(payload)}")
    if not payload:
        return (None, None)
    results = payload.get("results")
    if results is None:
        return (None, None)
    if not isinstance(results, dict):
        raise ValueError(f"results が辞書でない: {results!r}")
    if not results:
        return (None, None)
    muni_cd = results.get("muniCd")
    if muni_cd is None:
        return (None, None)
    return (str(muni_cd).zfill(5), results.get("lv01Nm"))


def revgeo_key(lat: float, lon: float) -> str:
    return f"{lat:.{COORD_DIGITS}f},{lon:.{COORD_DIGITS}f}"


def load_revgeo(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    """取得済みの逆ジオコーディング結果(JSON Lines)を読む。"""
    path = pathlib.Path(path)
    if not path.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out[row["key"]] = row
    return out
