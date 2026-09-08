# Kofun Atlas AI

日本古墳 時空間・地形・AI 分析アトラス。
公開・再利用可能なオープンデータだけを統合し、古墳の分布・年代・地形・AI 特徴量を
**ブラウザの中だけで**探索する静的 Web アプリ。

> 本アプリは公開・再利用可能な資料を統合したものであり、
> **日本国内の全古墳を網羅するものではありません。**

## いまの状態

**L0（立ち上げ）完了。** 収録 2,805 件（Geoshape 2,808 行 → 重複 3 行を統合）。
地図・類似検索・AI 分析はこれから実装する。進め方は [SPEC.md](SPEC.md) §9 のループ計画を参照。

数値は `public/data/data-manifest.json` から画面へ流しており、
README のこの段落は手で書いた要約である（実測値は manifest が正本）。

## Data Sources

| 源 | 役割 | ライセンス / 条件 |
|---|---|---|
| 『日本歴史地名大系』施設・地点項目データセット（CODH） | 位置・名称・読み・住所 | CC BY 4.0 / doi:10.20676/00000456 |
| 国土地理院 逆ジオコーダ | 都道府県・市区町村 | 国土地理院コンテンツ利用規約 |
| 国土地理院 標高タイル | 地形特徴（派生値のみ再配布） | 同上 |
| Wikidata | QID・別名・時期・外部 ID | CC0 |
| 文化庁 国指定文化財等データベース | 指定文化財・解説（文字情報のみ） | 出典記載で利用可 |
| 全国遺跡報告総覧 | 文献への外部リンクのみ | 個別確認 |

奈良女子大『全国古墳データベース』は**学術研究限定・改変および再配布禁止**のため、
データを取り込まない。Sources ページに参照 URL を記すにとどめる。

詳細は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## Architecture

```text
公開データ  →  Python パイプライン  →  GitHub  →  Vercel（静的）
                fetch / normalize
                entity resolution
                terrain features
                PyTorch → ONNX
                                        ブラウザで ONNX 推論・検索・フィルタ
```

学習はオフライン。本番はサーバ関数・DB・cron を持たない（`/api/health` を除く）。

## Development

```bash
git clone https://github.com/tetsuro-sakata/kofun-atlas-ai.git
cd kofun-atlas-ai

# Web
pnpm install
pnpm dev

# データ / ML
py -3.14 -m venv .venv          # Windows。他所では python3 -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

**別プロジェクトの venv が有効なまま走ることがある。** 依存を入れる前に
`python -c "import sys; print(sys.prefix)"` で行き先を確かめること。

## Data Pipeline

```bash
./.venv/Scripts/python.exe scripts/fetch_geoshape.py     # 取得 + manifest（既にあれば sha 検査のみ）
./.venv/Scripts/python.exe scripts/normalize.py          # → data/interim/kofun_l0.json
./.venv/Scripts/python.exe scripts/build_web_assets.py   # → public/data/data-manifest.json
```

Wikidata と文化庁は**人手スナップショット**である。手順は
[data/raw/wikidata/README.md](data/raw/wikidata/README.md) と
[data/raw/bunka/README.md](data/raw/bunka/README.md) を参照。

## Tests

```bash
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe harness/text_hygiene.py
pnpm typecheck && pnpm build
```

ケースと期待値の出所は [TEST_SPEC.md](TEST_SPEC.md)。

## Licenses

```text
CODE    MIT
DATA    源ごとの条件に従う（一括して MIT にはしない）
MODELS  プロジェクト定義 + 源の制約
```

## Limitations

- 全国約 16 万基の完全収録ではない。件数は**収録データセット内の件数**である
- AI の出力は特徴の類似度であって、考古学上の系統関係や歴史的事実ではない
- 欠測は「存在しない」ではなく「確認できない」を含む
- 未発見古墳の探索・精密候補座標の公開は行わない

## Citation

```text
『日本歴史地名大系』施設・地点項目データセット（CODH作成）
doi:10.20676/00000456 / CC BY 4.0
```
