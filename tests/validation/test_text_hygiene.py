"""T-014 / G-12: 日本語本文への別字種・制御文字の混入検査(HC-072)。"""

from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.validation


def test_t014_no_foreign_scripts_or_control_chars(project_root):
    proc = subprocess.run(
        [sys.executable, str(project_root / "harness" / "text_hygiene.py")],
        cwd=project_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"text_hygiene 違反:\n{proc.stdout}\n{proc.stderr}"
