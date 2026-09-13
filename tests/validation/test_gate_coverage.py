"""T-015 / G-16: SPEC の品質ゲートと TEST_SPEC のケースの対応を機械で数える。

SPEC の品質ゲート表は宣言であって実装でも検査でもない(HC-157)。
テストは自分が書いた分しか主張せず、書き忘れたゲートについては沈黙する。
だから対応そのものを検査する。

**表の書式に乗らない**(HC-080)。最初の版は表の先頭の欄が ID そのものだと仮定して
辞書の鍵にしていたので、先頭の欄を「G-26 二実装照合」と説明つきで書いた結果の表を
SPEC に足したら、鍵がケース表の「G-26」と一致せず偽の孤児ゲートを 3 件出した(2026-09-14)。
先頭の欄からゲート ID を正規表現で取り出す。
"""

from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.validation

GATE_RE = re.compile(r"G-\d{2}")
# 表の先頭の欄が「G-xx」で**始まる**行だけをゲートの行とみなす。
LEADING_GATE_RE = re.compile(r"^(G-\d{2})\b")


def _spec_gates(spec_text: str) -> dict[str, str]:
    """SPEC の表から `G-xx` → 状態欄 を拾う。

    同じ ID が複数の表に出るときは**後に出た行**を採る(§7 のゲート表は §3 の宣言表より後ろにある)。
    状態欄は行の最後の欄。
    """
    gates: dict[str, str] = {}
    for line in spec_text.splitlines():
        if not line.startswith("| G-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        match = LEADING_GATE_RE.match(cells[0])
        if not match:
            continue
        gates[match.group(1)] = cells[-1]
    return gates


def test_t015_every_gate_is_covered_or_declared_unimplemented(project_root):
    spec = (project_root / "SPEC.md").read_text(encoding="utf-8")
    test_spec = (project_root / "TEST_SPEC.md").read_text(encoding="utf-8")

    gates = _spec_gates(spec)
    assert gates, "SPEC からゲートを 1 件も拾えていない。検査が空振りしている"

    referenced = {
        g
        for line in test_spec.splitlines()
        if line.startswith("| T-")
        for g in GATE_RE.findall(line)
    }
    assert referenced, "TEST_SPEC のケース表からゲート参照を 1 件も拾えていない"

    orphans = [
        gid
        for gid, status in gates.items()
        if gid not in referenced and "未実装" not in status
    ]
    assert orphans == [], (
        f"どのケースからも参照されず、未実装とも書かれていないゲート: {orphans}"
    )


def test_t015_unimplemented_gates_are_listed_in_test_spec(project_root):
    """SPEC で「未実装」としたゲートは TEST_SPEC の末尾にも列挙されている。

    片側だけを直すと、二つの文書が静かに食い違う。
    """
    spec = (project_root / "SPEC.md").read_text(encoding="utf-8")
    test_spec = (project_root / "TEST_SPEC.md").read_text(encoding="utf-8")

    unimplemented = {
        gid for gid, status in _spec_gates(spec).items() if "未実装" in status
    }
    tail = test_spec.split("### 未実装のゲート")[-1]
    listed = set(GATE_RE.findall(tail))
    assert unimplemented == listed, (
        f"SPEC 側 {sorted(unimplemented)} と TEST_SPEC 側 {sorted(listed)} が食い違う"
    )


def test_t015_positive_control_detects_an_orphan_gate():
    """T-015 の陽性対照: 参照も未実装宣言も無いゲートを実際に捕まえる。"""
    spec = "| ID | ゲート | 判定 | 状態 |\n| G-99 | 架空 | 件数 | L0 実装 |\n"
    gates = _spec_gates(spec)
    assert gates == {"G-99": "L0 実装"}
    referenced: set[str] = set()
    orphans = [g for g, s in gates.items() if g not in referenced and "未実装" not in s]
    assert orphans == ["G-99"]


def test_t015_positive_control_described_id_is_still_an_orphan():
    """直した後も緩んでいないこと: 先頭の欄が説明つきでも、未参照なら孤児として捕まえる。"""
    spec = "| ゲート | 結果 |\n| G-98 説明つきの架空ゲート | 全件一致 |\n"
    gates = _spec_gates(spec)
    assert gates == {"G-98": "全件一致"}, "説明つきの ID からゲートを取り出せていない"
    referenced = {"G-01"}
    orphans = [g for g, s in gates.items() if g not in referenced and "未実装" not in s]
    assert orphans == ["G-98"]


def test_t015_negative_control_non_gate_rows_are_ignored():
    """ゲートでない行(本文中で G-xx に言及するだけの行)は拾わない。"""
    spec = "| 事項 | 値 |\n| 参考 | G-12 を見よ |\n| Gate | G-12 |\n"
    assert _spec_gates(spec) == {}
