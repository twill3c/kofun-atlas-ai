"""Geoshape / CODH の POI CSV を取得して manifest を残す。

    python scripts/fetch_geoshape.py            # 取得(既にあれば再取得しない)
    python scripts/fetch_geoshape.py --force    # 取り直す

CI からは呼ばない(構想書 §40.2)。データ更新は手動実行を基本にする。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from kofun_atlas import geoshape  # noqa: E402

DATASET_URL = (
    "https://geoshape.ex.nii.ac.jp/nrct-poi/dataset/nrct-poi-20250515.csv"
)
DATASET_VERSION = "2025-05-15"
OUT_DIR = pathlib.Path(__file__).resolve().parents[1] / "data" / "raw" / "geoshape"
CSV_PATH = OUT_DIR / "nrct-poi-20250515.csv"
MANIFEST_PATH = OUT_DIR / "manifest.json"

USER_AGENT = "KofunAtlasAI/1.0 (research prototype; https://github.com/)"
TIMEOUT_S = 180


def download(force: bool) -> bool:
    """必要なら取得する。実際に取得したかどうかを返す。"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if CSV_PATH.exists() and not force:
        print(f"既にある: {CSV_PATH}(取り直すには --force)")
        return False
    resp = requests.get(DATASET_URL, timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    CSV_PATH.write_bytes(resp.content)
    print(f"取得: {CSV_PATH}({len(resp.content):,} バイト)")
    return True


def _retrieved_at(downloaded: bool, sha256: str) -> str:
    """取得日を決める。

    ファイルの mtime から推測してはならない —— 複製やクローンで mtime は
    その日に書き換わるので、**取得していない日を「取得日」として出荷してしまう**。
    取得した回だけ今日を刻み、それ以外は既存の manifest を引き継ぐ。
    """
    if downloaded:
        return dt.date.today().isoformat()
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"{CSV_PATH} はあるが {MANIFEST_PATH} が無い。取得日が分からないので "
            "--force で取り直すこと"
        )
    previous = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if previous.get("sha256") != sha256:
        raise ValueError(
            "CSV の内容が manifest の sha256 と一致しない。"
            "手で置き換えたなら --force で取り直すこと"
        )
    return previous["retrieved_at"]


def write_manifest(path: pathlib.Path, downloaded: bool) -> dict:
    body = path.read_bytes()
    sha256 = hashlib.sha256(body).hexdigest()
    retrieved = _retrieved_at(downloaded, sha256)
    candidates = geoshape.load_candidates(path)
    manifest = {
        "source": geoshape.SOURCE_ID,
        "url": DATASET_URL,
        "source_version": DATASET_VERSION,
        "retrieved_at": retrieved,
        "license": geoshape.SOURCE_LICENSE,
        "credit": geoshape.SOURCE_CREDIT,
        "bytes": len(body),
        "sha256": sha256,
        "kofun_candidates": len(candidates),
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="既存ファイルを取り直す")
    args = parser.parse_args()

    downloaded = download(args.force)
    manifest = write_manifest(CSV_PATH, downloaded)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
