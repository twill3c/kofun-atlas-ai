"""古墳の座標を国土地理院 逆ジオコーダにかけ、結果を JSON Lines へ貯める。

    python scripts/fetch_revgeo.py            # 未取得の座標だけを取る(再開可能)
    python scripts/fetch_revgeo.py --limit 50 # 試し取り

出力 `data/raw/gsi/revgeo.jsonl` はリポジトリに入れる。
そうすれば CI も他人のクローンも**一度も国土地理院を叩かずに**同じ結果を再現できる。

HC-221 の三点を守る:
- 結果はキャッシュし、途中で落ちても続きから再開する(追記のみ)
- 時間のかかる取得には間を空けた再試行を入れる
- **「無い」という答えは再試行しない** —— 逆ジオコーダの `{}` は
  「陸上でない」という答えであって障害ではない
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from kofun_atlas import geocode, geoshape  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "raw" / "geoshape" / "nrct-poi-20250515.csv"
OUT_PATH = ROOT / "data" / "raw" / "gsi" / "revgeo.jsonl"
MANIFEST_PATH = ROOT / "data" / "raw" / "gsi" / "manifest.json"

USER_AGENT = "KofunAtlasAI/1.0 (research prototype; https://github.com/)"
# 1 件あたりの応答は約 1.75 秒(2026-09-08 実測)。直列だと 2,700 件で 80 分を超える。
# 4 並列で約 2.3 件/秒。公的サービスへの負荷としては控えめな範囲に収める。
WORKERS = 4
DELAY_S = 0.05  # 各ワーカーが 1 件ごとに入れる間
TIMEOUT_S = 30
MAX_ATTEMPTS = 4
BACKOFF_S = (2, 6, 15)


def fetch_one(lat: float, lon: float) -> dict:
    """1 点を引く。一時的な失敗だけ間を空けて再試行する。"""
    url = f"{geocode.REVGEO_URL}?lat={lat}&lon={lon}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                # 「無い」は答えであって障害ではない。待っても変わらない。
                return {}
            last = exc
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last = exc
        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(BACKOFF_S[attempt])
    raise RuntimeError(f"{lat},{lon} の取得に {MAX_ATTEMPTS} 回失敗した: {last}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="取得する件数の上限")
    args = parser.parse_args()

    candidates = geoshape.load_candidates(CSV_PATH)
    done = geocode.load_revgeo(OUT_PATH)

    wanted: dict[str, tuple[float, float]] = {}
    for cand in candidates:
        wanted.setdefault(geocode.revgeo_key(cand.lat, cand.lon), (cand.lat, cand.lon))

    todo = [(k, v) for k, v in wanted.items() if k not in done]
    if args.limit is not None:
        todo = todo[: args.limit]

    print(
        f"座標 {len(wanted):,} 種 / 取得済み {len(done):,} / これから {len(todo):,}",
        flush=True,
    )

    def work(item: tuple[str, tuple[float, float]]) -> dict:
        key, (lat, lon) = item
        payload = fetch_one(lat, lon)
        muni_cd, lv01 = geocode.parse_response(payload)
        time.sleep(DELAY_S)
        return {
            "key": key,
            "lat": lat,
            "lon": lon,
            "muni_cd": muni_cd,
            "lv01Nm": lv01,
            "retrieved_at": dt.date.today().isoformat(),
        }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    started = time.monotonic()
    with OUT_PATH.open("a", encoding="utf-8", newline="\n") as fh:
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for row in pool.map(work, todo):
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                written += 1
                if written % 100 == 0:
                    fh.flush()
                    rate = written / (time.monotonic() - started)
                    remain = (len(todo) - written) / rate / 60
                    print(
                        f"  {written:,}/{len(todo):,}  {rate:.2f} 件/秒  残り {remain:.1f} 分",
                        flush=True,
                    )

    total = geocode.load_revgeo(OUT_PATH)
    unresolved = sum(1 for r in total.values() if r["muni_cd"] is None)
    manifest = {
        "source": geocode.SOURCE_ID,
        "url": geocode.REVGEO_URL,
        "muni_table_url": geocode.MUNI_URL,
        "retrieved_at": dt.date.today().isoformat(),
        "license": "国土地理院コンテンツ利用規約",
        "credit": "出典：国土地理院ウェブサイト",
        "coordinates": len(total),
        "unresolved": unresolved,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"追記 {written:,} 件 / 総数 {len(total):,} / 陸上でない {unresolved:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
