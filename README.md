# Kofun Atlas AI

日本古墳 時空間・地形・AI 分析アトラス。
公開・再利用可能なオープンデータだけを統合し、古墳の分布・年代・地形・AI 特徴量を
**ブラウザの中だけで**探索する静的 Web アプリ。

> 本アプリは公開・再利用可能な資料を統合したものであり、
> **日本国内の全古墳を網羅するものではありません。**

## いまの状態

**L6（探索・比較・作り方・出典）完了。** 収録 2,805 件（Geoshape 2,808 行 → 重複 3 行を統合）、
46 都道府県、地形特徴 2,804 件、立地の埋め込みと二次元配置 2,805 件。

| ページ | できること |
|---|---|
| `/map/` | 全件を地図に並べ、都道府県で絞り、名前で探し、古墳を選ぶと地形と**立地の似た古墳（上位 10 件）**を出す |
| `/explore/` | 立地の二次元配置（t-SNE）と日本の縮小地図を並べ、標高・傾斜・周囲より高い度合いの 5 分位で塗る。範囲選択と県の強調が一覧表に反映される |
| `/compare/` | 都道府県ごとの収録件数と地形の中央値の表 |
| `/methodology/` | データの集め方・計算・確かめ方と、していないこと。数値は manifest と指標ファイルから読む |
| `/sources/` | 出典と取り込みの状況、偏りの注意 |

公開（GitHub・Vercel）は L7 で行う。進め方は [SPEC.md](SPEC.md) §9 のループ計画を参照。

> **箸墓古墳は収録されていない。** 収録元は『日本歴史地名大系』の見出し項目で、
> 考古学上の重要度で選ばれた一覧ではない。点の多い少ないは、その地域の古墳の多さではなく
> 元データにどれだけ載っているかを表す（[SPEC.md](SPEC.md) §3.12）。

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
git clone https://github.com/twill3c/kofun-atlas-ai.git
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

## 実ブラウザ検品

テストが緑でも画面が動くとは限らない。出荷される `out/` を静的配信して実際のブラウザで開き、
**在存ではなく幾何と到達**を測る（地図に描かれた点の数・視野に入った強調の数・出典のコントラスト・
複数の画面幅での溢れ・フッタの宛先）。

```bash
pnpm build            # → out/
pnpm smoke            # node harness/smoke-run.mjs。0 = 合格 / 1 = 不合格 / 2 = 前提不足 / 3 = 検品器が落ちた(読み込めない場合も 3)
node harness/smoke.mjs --shot   # 地図の撮影も行う(artifacts/screenshots/)
```

成否は終了コードで読む。`| tail` を挟むと `$?` が tail のものにすり替わる。
検品器の陽性対照（層を隠す・データを空にする・本文色を漏らす・空白を注入する）は同じ実行の中で撃つ。

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
