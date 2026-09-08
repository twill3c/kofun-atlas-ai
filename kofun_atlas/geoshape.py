"""Geoshape / CODH『日本歴史地名大系』施設・地点項目データセットの読み取り。

ライセンス: CC BY 4.0 / doi:10.20676/00000456

候補集合は **`分類3` だけ** で決める(SPEC §3.1)。
構想書 §11.1 の名称正規表現は、このデータセットでは足すものが無く
落とすものがあることを実測したので採らない。
"""

from __future__ import annotations

import csv
import dataclasses
import pathlib

SOURCE_ID = "geoshape"
SOURCE_URL = "https://geoshape.ex.nii.ac.jp/nrct-poi/index.html.ja"
SOURCE_LICENSE = "CC BY 4.0"
SOURCE_CREDIT = (
    "『日本歴史地名大系』施設・地点項目データセット(CODH作成) doi:10.20676/00000456"
)

# 採録する分類(SPEC §2)。
KOFUN_CATEGORY = "古墳"
# 採録しない近隣分類。検査が空振りしていないことを確かめるために名前で持つ。
EXCLUDED_CATEGORIES = ("貝塚", "天皇陵", "横穴群")

REQUIRED_COLUMNS = (
    "id",
    "都道府県コード",
    "名称",
    "読み",
    "住所",
    "緯度",
    "経度",
    "分類1",
    "分類2",
    "分類3",
)

# 日本の範囲(構想書 §8 の JSON Schema と同じ値)。
LAT_MIN, LAT_MAX = 20.0, 50.0
LON_MIN, LON_MAX = 120.0, 155.0


@dataclasses.dataclass(frozen=True)
class Candidate:
    """Geoshape 1 行から取り出した古墳候補。"""

    source_id: str
    name: str
    kana: str
    address: str
    pref_code: str
    lat: float
    lon: float

    @property
    def address_tokens(self) -> list[str]:
        return self.address.split()

    @property
    def municipality_hint(self) -> str | None:
        """住所の 2 番目のトークン(市区町村)。

        実測(2026-09-08・古墳 2,808 件): 住所は例外なく空白区切り 3 トークンで、
        2 番目が市区町村。県名トークンは 1,571 件で県コードと食い違うため採らないが、
        市区町村トークンは逆ジオコーダで確かめた 2 件の反例でも一致していた。
        あくまで**手がかり**であり、確定は L1 の逆ジオコーディングで行う。
        """
        tokens = self.address_tokens
        return tokens[1] if len(tokens) >= 2 else None


def is_inside_japan(candidate: Candidate) -> bool:
    return LAT_MIN <= candidate.lat <= LAT_MAX and LON_MIN <= candidate.lon <= LON_MAX


def load_candidates(csv_path: pathlib.Path) -> list[Candidate]:
    """CSV から古墳候補を取り出す。

    列名が変わったら黙って空を返すのではなく落ちる(HC-075)。
    """
    with pathlib.Path(csv_path).open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(
                f"Geoshape CSV に想定した列が無い: {missing} / 実際: {reader.fieldnames}"
            )
        rows = [r for r in reader if r["分類3"] == KOFUN_CATEGORY]

    if not rows:
        raise ValueError(
            f"分類3 == {KOFUN_CATEGORY!r} の行が 1 件も無い。"
            "データセットの分類体系が変わった可能性がある"
        )

    candidates = [
        Candidate(
            source_id=r["id"],
            name=r["名称"],
            kana=r["読み"],
            address=r["住所"],
            pref_code=r["都道府県コード"],
            lat=float(r["緯度"]),
            lon=float(r["経度"]),
        )
        for r in rows
    ]

    seen = {c.source_id for c in candidates}
    if len(seen) != len(candidates):
        raise ValueError("Geoshape の id が重複している。名寄せの前提が崩れている")
    return candidates
