"""内部 ID の採番(SPEC §8 / 構想書 §10)。

内部 ID はデータソースの ID に依存させない。同じ古墳が複数の源に現れても
同じ ID に落ち、源の ID 体系が変わっても壊れないようにするため。
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

ID_PREFIX = "kofun_"
ID_HEX_LEN = 10
COORD_DIGITS = 4

_WS = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """名称の正規化(構想書 §12.1)。

    1. Unicode NFKC(全角・半角の統一を含む)
    2. 前後の空白を落とし、内部の連続空白を 1 つにまとめる

    「古墳」「墳」等の接尾辞は**落とさない**。別名候補の生成には使うが、
    名前そのものは保つ(構想書 §12.1 の 6)。
    """
    return _WS.sub(" ", unicodedata.normalize("NFKC", name)).strip()


def canonical_text(
    *,
    name: str,
    prefecture: str | None,
    municipality: str | None,
    lat: float,
    lon: float,
) -> str:
    """ID の素になる文字列。

    座標は小数第 4 位へ丸める。第 4 位はおよそ 11 m にあたり、
    同一地点を指す表記ゆれを吸収しつつ、隣接する古墳を潰さない粒度である。
    """
    return "|".join(
        [
            normalize_name(name),
            prefecture or "",
            municipality or "",
            f"{round(lat, COORD_DIGITS):.{COORD_DIGITS}f}",
            f"{round(lon, COORD_DIGITS):.{COORD_DIGITS}f}",
        ]
    )


def id_from_canonical_text(text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return ID_PREFIX + digest[:ID_HEX_LEN]


def kofun_id(
    *,
    name: str,
    prefecture: str | None,
    municipality: str | None,
    lat: float,
    lon: float,
) -> str:
    return id_from_canonical_text(
        canonical_text(
            name=name,
            prefecture=prefecture,
            municipality=municipality,
            lat=lat,
            lon=lon,
        )
    )
