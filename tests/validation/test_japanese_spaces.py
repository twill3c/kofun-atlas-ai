"""T-069: 画面の文字列の中の「和文␣和文」を、ビルドの前にソースで拾う。

実ブラウザ検品(`harness/smoke.mjs`)も描画された本文で同じ形を拾うが、ビルドと配信の後でしか走らない。
loop_006 では出典名を「国土地理院 標高タイル」のように**組織名と名称を半角空白で区切って**書き、
検品器で 5 箇所見つかった。同じ行に書いた空白はソースを読めば分かるので、ここで先に落とす。

JSX の本文を行の途中で改行した場合(改行と字下げが空白一つに畳まれる・loop_005)はソースの一行には
現れないので、そちらは引き続き検品器の担当である。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# harness/smoke.mjs の strayJapaneseSpaces と同じ字の範囲にそろえる
JA = "[぀-ヿ㐀-鿿　-〿（），：]"
PATTERN = re.compile(f"(?=({JA}) ({JA}))")
# 「␣・␣」は区切りとして意図した形(フリート共通フッタの規約「MIT License © 2026 坂田哲朗 ・ GitHub ・ …」)。
# 最初の実行でフッタの注記のこの形を 4 件拾った。中黒の両側の空白だけを除外する。
SEPARATOR = "・"


def stray_spaces(text: str) -> list[str]:
    hits = []
    for m in PATTERN.finditer(text):
        if SEPARATOR in (m.group(1), m.group(2)):
            continue
        hits.append(text[max(0, m.start() - 8) : m.start() + 11])
    return hits


def test_source_has_no_space_between_japanese() -> None:
    files = sorted((ROOT / "src").rglob("*.ts")) + sorted((ROOT / "src").rglob("*.tsx"))
    assert len(files) >= 10, f"走査対象が少なすぎる(src の場所を誤っていないか): {len(files)}"
    found = []
    for path in files:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for hit in stray_spaces(line):
                found.append(f"{path.relative_to(ROOT)}:{lineno}: …{hit}…")
    # 件数を先に出す(例を切ると、見えた分だけ直して残りを持ち越す・loop_006)
    assert not found, f"{len(found)} 件\n" + "\n".join(found)


def test_positive_control_catches_the_shapes_seen() -> None:
    # loop_006 で実際に出た形と、区切りとして正しい形
    assert stray_spaces('source: "国土地理院 標高タイル"')
    assert stray_spaces("重なりの割合 半径 2")
    assert stray_spaces("（DEM5A） 淡色地図")
    assert not stray_spaces("国土地理院「標高タイル」")
    assert not stray_spaces("半径 2: 87.7%")
    assert not stray_spaces("標高 m")
    # 意図した区切りは拾わないが、区切りの隣でない空白は同じ行でも拾う
    assert not stray_spaces("坂田哲朗 ・ GitHub ・ 歩き方 ・ 設計図")
    assert len(stray_spaces("歩き方 ・ 設計図 と 古墳")) == 2
