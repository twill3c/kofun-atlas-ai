"""T-073: 画面の文言に「これから作る」型の未来の約束や、ループの段階名が残っていない。

L7(2026-09-15)の公開直前に、トップページが「いまの状態(L4)」「二次元配置の探索画面はこれから作ります」の
まま L6 まで残っていた。出典のページも、V1.0 で使わないと決めた源の役割に「（予定）」と書いていた。
数値は manifest から読むので正しく変わり、**隣の散文だけが古いまま残る**(HC-280)。検品器は構造・件数・
リンクを測っていて、散文の時制を見る項目が無かった。

走査するのは `src/app` と `src/components` の、コメントでない行である
(コメントにはループの経緯として L0 / L7 を書く)。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 公開した画面に残ってはいけない言い回し。見つけた形そのもの
MARKERS = re.compile(r"これから作|今後作|予定）|（予定|準備中|段階的に作|いまの状態")
# 画面にループの段階名(L0〜L9)を出さない。英字に続く L や型名の一部は除く
LOOP_LABEL = re.compile(r"(?<![A-Za-z0-9_])L[0-9](?![0-9A-Za-z_])")
COMMENT = re.compile(r"^\s*(//|/\*|\*|\{/\*)")


def findings(text: str) -> list[str]:
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if COMMENT.match(line):
            continue
        for pattern in (MARKERS, LOOP_LABEL):
            for m in pattern.finditer(line):
                hits.append(f"{lineno}: {m.group(0)} … {line.strip()[:60]}")
    return hits


def test_screen_sources_have_no_stale_prose() -> None:
    files = sorted((ROOT / "src" / "app").rglob("*.tsx")) + sorted((ROOT / "src" / "components").rglob("*.tsx"))
    assert len(files) >= 6, f"走査対象が少なすぎる: {len(files)}"
    found = [f"{p.relative_to(ROOT)}:{hit}" for p in files for hit in findings(p.read_text(encoding="utf-8"))]
    assert not found, f"{len(found)} 件\n" + "\n".join(found)


def test_positive_control_catches_the_shapes_seen() -> None:
    # 実際に残っていた形
    assert findings("        <h2>いまの状態（{stage}）</h2>")
    assert findings("          二次元配置の探索画面はこれから作ります。")
    assert findings('    role: "別名・時期などの補完（予定）",')
    assert findings("  <p>段階 L4 まで完了</p>")
    # 拾わない形: コメントの経緯・英字に続く L・数値の一部
    assert not findings(" * 公開ループ(L7)で作るので、")
    assert not findings("  // L0 では捏造した URL を直書きしていた")
    assert not findings('  const HTML5 = "L10n";')
