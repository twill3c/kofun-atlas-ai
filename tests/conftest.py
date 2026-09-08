"""共通フィクスチャ。

パスはプロジェクト直下からの絶対パスで解決する(HC-038: cwd を持ち越さない)。

**skip は緑と見分けが付かない。** 生成物が無いときの skip は手元では親切だが、
CI でそれが起きると「検査した」と「検査しなかった」が同じ出力になる。
`KOFUN_REQUIRE_ARTIFACTS=1` を立てたときは skip せず落ちるようにして、
CI ではそれを立てる。
"""

from __future__ import annotations

import os
import pathlib
import sys

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

GEOSHAPE_CSV = PROJECT_ROOT / "data" / "raw" / "geoshape" / "nrct-poi-20250515.csv"
PROCESSED = PROJECT_ROOT / "data" / "processed" / "kofun.json"
FIXTURES = PROJECT_ROOT / "tests" / "fixtures"


def _require_or_skip(path: pathlib.Path, how: str) -> pathlib.Path:
    if path.exists():
        return path
    message = f"{path} が無い。{how}"
    if os.environ.get("KOFUN_REQUIRE_ARTIFACTS"):
        pytest.fail(message)
    pytest.skip(message)


@pytest.fixture(scope="session")
def project_root() -> pathlib.Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def geoshape_csv() -> pathlib.Path:
    return _require_or_skip(
        GEOSHAPE_CSV, "`python scripts/fetch_geoshape.py` で取得すること"
    )


@pytest.fixture(scope="session")
def processed_path() -> pathlib.Path:
    return _require_or_skip(
        PROCESSED, "`python scripts/geocode_records.py` を先に実行すること"
    )


@pytest.fixture(scope="session")
def fixtures_dir() -> pathlib.Path:
    return FIXTURES
