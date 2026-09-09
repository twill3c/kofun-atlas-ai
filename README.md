# Kofun Atlas AI

日本古墳 時空間・地形・AI 分析アトラス。
公開・再利用可能なオープンデータだけを統合し、古墳の分布・年代・地形・AI 特徴量を
**ブラウザの中だけで**探索する静的 Web アプリ。

> 本アプリは公開・再利用可能な資料を統合したものであり、
> **日本国内の全古墳を網羅するものではありません。**

## いまの状態

**L4（二次元配置）完了。** 収録 2,805 件（Geoshape 2,808 行 → 重複 3 行を統合）、
46 都道府県、地形特徴 2,804 件、立地の埋め込みと二次元配置 2,805 件。
地図と探索画面はこれから実装する。進め方は [SPEC.md](SPEC.md) §9 のループ計画を参照。

> **クラスタリングは測って落とした。** どの設定でもノイズ率が 50% を超え
> （`min_cluster_size=30` で 92.5%）、全体を群に切れなかった。立地は連続していて
> はっきりした型に分かれない、というのが実測の結果である。詳細は [SPEC.md](SPEC.md) §3.11。

> **AI が扱うのは「立地」だけである。**
> 墳形・墳丘長・築造時期・出土品は、再配布できる公開データでは 1 件も埋まっていない
> （実測 2,805 件中 0 件）。したがって埋め込みは
> **その古墳が置かれた場所**を表すもので、考古学上の系統関係や編年を示さない。
> 詳細は [model-card](public/models/model-card.md) と [SPEC.md](SPEC.md) §3.7。

地形は国土地理院の標高タイル（z14・±1,000 m の窓）から算出している。
**層は画素単位で合成する** — DEM5A はタイルが存在しても中身の大半が NoData の
ことがあり、必要タイル 6,597 枚のうち 6,213 枚（94.2%）が二層以上の重ね合わせを
必要とした（[SPEC.md](SPEC.md) §3.5）。水面には標高がないので `null` のまま残す。

都道府県は元データの県名・県コードではなく**座標から国土地理院の逆ジオコーダで確定**している。
元データではこの二欄が食い違っており、しかもどちらが正しいかは行ごとに違った
（[SPEC.md](SPEC.md) §3.2）。県コードを信じると沖縄県に 11 基の古墳が現れるが、
実際は 11 件とも鹿児島県である。

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
./.venv/Scripts/python.exe scripts/geocode_records.py    # → data/processed/kofun.json
./.venv/Scripts/python.exe scripts/apply_terrain.py      # 同梱の地形特徴を載せる
./.venv/Scripts/python.exe scripts/build_web_assets.py   # → public/data/data-manifest.json
```

逆ジオコーディングの結果（`data/raw/gsi/revgeo.jsonl`）と国土地理院の市区町村表
（`data/raw/gsi/muni.js`）はリポジトリに同梱してある。**再取得は不要**で、
CI もクローンも国土地理院を一度も叩かずに同じ結果を再現できる。
座標を足したときだけ次を走らせる（追記のみ・途中で落ちても再開できる）。

```bash
./.venv/Scripts/python.exe scripts/fetch_revgeo.py
```

地形特徴も同じ考え方で、派生値（`data/derived/terrain.jsonl`）だけを同梱している。
**全国 DEM そのものは再配布しない。** 標高タイルを取り直して計算し直すのは
座標を足したときだけで、その場合は次を走らせる（キャッシュは約 550 MB になる）。

```bash
./.venv/Scripts/python.exe scripts/fetch_dem.py          # タイルを取得(ローカルのみ)
./.venv/Scripts/python.exe scripts/terrain_features.py   # → data/derived/terrain.jsonl
```

Wikidata と文化庁は**人手スナップショット**である。手順は
[data/raw/wikidata/README.md](data/raw/wikidata/README.md) と
[data/raw/bunka/README.md](data/raw/bunka/README.md) を参照。

## Training

学習済みの埋め込みと ONNX はリポジトリに同梱してある（合計 0.3 MB）。
**再学習は不要**で、CI も学習を回さない。作り直すときだけ次を走らせる（各約 10 分）。

```bash
./.venv/Scripts/python.exe ml/train_encoder.py     # → public/data/embeddings.json
./.venv/Scripts/python.exe ml/export_onnx.py       # → public/models/kofun_encoder.onnx
./.venv/Scripts/python.exe ml/model_card.py        # → public/models/model-card.md
./.venv/Scripts/python.exe ml/build_projection.py  # → public/data/projection.json
```

再現性の確認（手元専用・出力は同梱しない）:

```bash
./.venv/Scripts/python.exe ml/train_encoder.py --seed 42 --out-suffix=-seed42b
./.venv/Scripts/python.exe ml/train_encoder.py --seed 7  --out-suffix=-seed7
```

`--out-suffix` の値は `-` で始まるので `=` で渡す（空白区切りだと argparse が
オプションと解釈する）。

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
