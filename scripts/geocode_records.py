"""L0 の暫定レコードに逆ジオコーディングを当て、出荷レコードを作る。

    python scripts/geocode_records.py

入力:
  data/interim/kofun_l0.json     — scripts/normalize.py の出力
  data/raw/gsi/revgeo.jsonl      — scripts/fetch_revgeo.py の出力(リポジトリ同梱)
  data/raw/gsi/muni.js           — 国土地理院 市区町村表(リポジトリ同梱)

出力:
  data/processed/kofun.json
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from kofun_atlas import geocode, records, schema  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim" / "kofun_l0.json"
REVGEO = ROOT / "data" / "raw" / "gsi" / "revgeo.jsonl"
MUNI = ROOT / "data" / "raw" / "gsi" / "muni.js"
GSI_MANIFEST = ROOT / "data" / "raw" / "gsi" / "manifest.json"
OUT = ROOT / "data" / "processed" / "kofun.json"


def main() -> int:
    for path in (INTERIM, REVGEO, MUNI, GSI_MANIFEST):
        if not path.exists():
            print(f"{path} が無い", file=sys.stderr)
            return 1

    interim = json.loads(INTERIM.read_text(encoding="utf-8"))
    revgeo = geocode.load_revgeo(REVGEO)
    table = geocode.load_muni_table(MUNI)
    retrieved_at = json.loads(GSI_MANIFEST.read_text(encoding="utf-8"))["retrieved_at"]

    missing = []
    out = []
    for rec in interim:
        key = geocode.revgeo_key(rec["location"]["lat"], rec["location"]["lon"])
        row = revgeo.get(key)
        if row is None:
            # 取得漏れは「陸上でない」と区別できない。黙って null にせず落とす。
            missing.append((rec["id"], key))
            continue
        entry = geocode.lookup_muni(row["muni_cd"], table)
        if row["muni_cd"] is not None and entry is None:
            raise ValueError(
                f"逆ジオコーダが返した muniCd {row['muni_cd']} が市区町村表に無い"
            )
        out.append(
            records.apply_geocode(
                rec, muni_entry=entry, lv01=row.get("lv01Nm"), retrieved_at=retrieved_at
            )
        )

    if missing:
        print(
            f"逆ジオコーディング未取得が {len(missing)} 件ある。"
            f"`python scripts/fetch_revgeo.py` を先に完走させること: {missing[:3]}",
            file=sys.stderr,
        )
        return 1

    duplicates = [k for k, v in collections.Counter(r["id"] for r in out).items() if v > 1]
    if duplicates:
        print(f"確定 ID が衝突した: {duplicates[:5]}", file=sys.stderr)
        return 1

    validator = schema.kofun_validator()
    errors = [
        (rec["id"], err.message) for rec in out for err in validator.iter_errors(rec)
    ]
    if errors:
        print(f"スキーマ違反 {len(errors)} 件: {errors[:5]}", file=sys.stderr)
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    unresolved = [r for r in out if r["muni_cd"] is None]
    prefs = collections.Counter(r["prefecture"] for r in out if r["prefecture"])
    changed = sum(
        1
        for r in out
        if r["muni_cd"] is not None
        and int(r["muni_cd"][:2]) != int(r["raw_extra"]["geoshape_pref_code"])
    )
    print(f"レコード {len(out):,} 件 / 陸上でない {len(unresolved):,} 件")
    print(f"都道府県 {len(prefs)} 種 / 上位 {prefs.most_common(5)}")
    print(f"CSV の県コードと食い違い、逆ジオコーダで直した件数: {changed:,}")
    print(f"書き出し: {OUT}({OUT.stat().st_size:,} バイト)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
