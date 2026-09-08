"""Geoshape 候補を `KofunRecord` へ正規化して `data/interim/` へ書く。

L0 の出力は **暫定** である。`prefecture` / `municipality` が未確定で、
内部 ID もそれに伴って L1 で振り直される(SPEC §8)。だから `data/processed/`
ではなく `data/interim/` に置き、出荷対象にしない。

    python scripts/normalize.py
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from kofun_atlas import geoshape, records, schema  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "raw" / "geoshape" / "nrct-poi-20250515.csv"
OUT_PATH = ROOT / "data" / "interim" / "kofun_l0.json"


def main() -> int:
    candidates = geoshape.load_candidates(CSV_PATH)
    normalized = records.normalize_all(candidates)

    validator = schema.kofun_validator()
    errors = [
        (rec["id"], err.message)
        for rec in normalized
        for err in validator.iter_errors(rec)
    ]
    if errors:
        print(f"スキーマ違反 {len(errors)} 件: {errors[:5]}", file=sys.stderr)
        return 1

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    merged = sum(
        len(r["raw_extra"].get("geoshape_duplicate_ids", [])) for r in normalized
    )
    hints = collections.Counter(
        r["raw_extra"]["geoshape_municipality_hint"] for r in normalized
    )
    print(f"候補 {len(candidates):,} 行 → レコード {len(normalized):,} 件(統合 {merged} 行)")
    print(f"市区町村の手がかり(未確定): {len(hints):,} 種")
    print(f"書き出し: {OUT_PATH}({OUT_PATH.stat().st_size:,} バイト)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
