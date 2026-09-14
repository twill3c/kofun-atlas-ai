"""T-074: 検査が読むモジュールが無いとき、手元では skip・CI(KOFUN_REQUIRE_ARTIFACTS=1)では失敗になる。

`pytest.importorskip` は CI で依存を入れ忘れても skip で緑にする。G-08 の ONNX 照合 3 件は
そうして CI で一度も走っていなかった(2026-09-15、新しい clone に CI を再現して発見)。
"""

from __future__ import annotations

import pytest

MISSING = "kofun_atlas_no_such_module_for_control"


def test_missing_module_is_skipped_locally(require_module, monkeypatch) -> None:
    monkeypatch.delenv("KOFUN_REQUIRE_ARTIFACTS", raising=False)
    with pytest.raises(pytest.skip.Exception):
        require_module(MISSING)


def test_missing_module_fails_under_ci_flag(require_module, monkeypatch) -> None:
    monkeypatch.setenv("KOFUN_REQUIRE_ARTIFACTS", "1")
    with pytest.raises(pytest.fail.Exception):
        require_module(MISSING)


def test_present_module_is_returned_either_way(require_module, monkeypatch) -> None:
    # 陽性対照の土台: 在るモジュールはどちらの設定でも返る(何でも落とす実装を通さない)
    for flag in (None, "1"):
        if flag is None:
            monkeypatch.delenv("KOFUN_REQUIRE_ARTIFACTS", raising=False)
        else:
            monkeypatch.setenv("KOFUN_REQUIRE_ARTIFACTS", flag)
        assert require_module("json").dumps([1]) == "[1]"
