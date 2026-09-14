"""T-070: G-13 公開静的アセットの合計が 60 MB 未満である。

配るのは `public/` の中身と、`next build` が作る `_next/` のチャンクである。CI の python ジョブでは
ビルドをしないので、ここでは **`public/` を必ず測り**、`out/`(静的書き出し)があればそれも測る。
`out/` の測定は実ブラウザ検品(`harness/smoke.mjs`)がビルドの後に必ず行う。

2026-09-15 実測: public/ 3,664,222 B、out/ 5,777,280 B(304 ファイル)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUDGET_BYTES = 60 * 1024 * 1024


def tree_bytes(directory: Path) -> tuple[int, int]:
    files = [p for p in directory.rglob("*") if p.is_file()]
    return sum(p.stat().st_size for p in files), len(files)


def within_budget(total: int, budget: int = BUDGET_BYTES) -> bool:
    return total < budget


def test_public_assets_under_budget() -> None:
    total, count = tree_bytes(ROOT / "public")
    # 前提: 測る対象が実在する(空のディレクトリを測って 0 B で通さない)
    assert count >= 5, f"public/ のファイルが少なすぎる: {count}"
    assert (ROOT / "public" / "data" / "kofun-points.geojson").is_file()
    assert within_budget(total), f"public/ が {total:,} B(上限 {BUDGET_BYTES:,} B)"


def test_export_under_budget_when_built() -> None:
    out = ROOT / "out"
    if not out.is_dir():
        pytest.skip("out/ が無い(静的書き出しの測定は smoke.mjs が担う)")
    total, _ = tree_bytes(out)
    assert within_budget(total), f"out/ が {total:,} B(上限 {BUDGET_BYTES:,} B)"


def test_positive_control_budget_detects_overflow() -> None:
    total, _ = tree_bytes(ROOT / "public")
    # 上限を実測より 1 B 小さくすれば落ちる / ちょうど同じでも「未満」ではないので落ちる
    assert not within_budget(total, budget=total - 1)
    assert not within_budget(total, budget=total)
    assert within_budget(total, budget=total + 1)
