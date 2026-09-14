"""T-075: CI の pnpm の版の指定が一か所だけである。

`package.json` に `packageManager` があるとき、`pnpm/action-setup` に `version` を重ねて書くと、
action は「Multiple versions of pnpm specified」で落ちる。GitHub 上の最初の実行(34900988678)で web ジョブが
これで落ちた。新しい clone に `CI=true` で再現したときは緑だった —— 再現スクリプトは workflow の `run:` の行を
なぞるだけで、**action そのものの入力検査は再現できない**。だからここで静的に見る。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def action_setup_versions(workflow_text: str) -> list[str]:
    """`uses: pnpm/action-setup` の step に付いた `with.version` を返す(無ければ空)。"""
    lines = workflow_text.splitlines()
    found = []
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)-\s+uses:\s*pnpm/action-setup", line)
        if not m:
            continue
        step_indent = len(m.group(1))
        for follow in lines[i + 1 :]:
            if not follow.strip() or follow.strip().startswith("#"):
                continue
            indent = len(follow) - len(follow.lstrip())
            if indent <= step_indent:
                break  # 次の step か、別の階層に出た
            v = re.match(r"^\s*version:\s*(\S+)", follow)
            if v:
                found.append(v.group(1).strip("\"'"))
    return found


def test_pnpm_version_is_declared_once() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert "pnpm/action-setup" in workflow, "前提: CI が pnpm/action-setup を使っている"
    assert package.get("packageManager", "").startswith("pnpm@"), "前提: packageManager で版を固定している"
    assert action_setup_versions(workflow) == [], "packageManager と action-setup の version が二重に指定されている"


def test_positive_control_detects_the_shape_that_failed() -> None:
    failed = """
jobs:
  web:
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 10

      - uses: actions/setup-node@v4
        with:
          node-version: 22
"""
    assert action_setup_versions(failed) == ["10"]
    fixed = failed.replace("        with:\n          version: 10\n", "")
    assert action_setup_versions(fixed) == []
    # 別の step の with(node-version)を拾わない
    assert "22" not in action_setup_versions(failed)
