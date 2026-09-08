"""共通フィクスチャ。

パスはプロジェクト直下からの絶対パスで解決する(HC-038: cwd を持ち越さない)。
"""

from __future__ import annotations

import pathlib
import sys

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

GEOSHAPE_CSV = PROJECT_ROOT / "data" / "raw" / "geoshape" / "nrct-poi-20250515.csv"
FIXTURES = PROJECT_ROOT / "tests" / "fixtures"


@pytest.fixture(scope="session")
def project_root() -> pathlib.Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def geoshape_csv() -> pathlib.Path:
    if not GEOSHAPE_CSV.exists():
        pytest.skip(
            "Geoshape CSV が無い。`python scripts/fetch_geoshape.py` で取得すること"
        )
    return GEOSHAPE_CSV


@pytest.fixture(scope="session")
def fixtures_dir() -> pathlib.Path:
    return FIXTURES
