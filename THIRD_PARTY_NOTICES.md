# THIRD_PARTY_NOTICES

本プロジェクトが利用する第三者データの帰属表示。

## Geoshape / CODH

```text
『日本歴史地名大系』施設・地点項目データセット（CODH作成）
doi:10.20676/00000456
Licensed under CC BY 4.0
https://geoshape.ex.nii.ac.jp/nrct-poi/index.html.ja
```

収録: `data/raw/geoshape/nrct-poi-20250515.csv`（2025-05-15 版・2026-09-08 取得）

## Wikidata

```text
Structured data from Wikidata, CC0
https://www.wikidata.org/wiki/Wikidata:Licensing
```

**V1.0 では取り込んでいない。** `query.wikidata.org/robots.txt` が `/sparql` を Disallow しているため
自動取得をやめ、人手スナップショットの手順だけを `data/raw/wikidata/README.md` に置いた。
スナップショットは置かれておらず、出荷物に Wikidata 由来の値は 0 件である。

## 国土地理院 / Geospatial Information Authority of Japan

```text
出典：国土地理院ウェブサイト
https://www.gsi.go.jp/

国土地理院の標高データを加工して作成
（elevation / slope / relief などの地形特徴量）

逆ジオコーディングに国土地理院の
「簡易逆ジオコーディングサービス」を利用
市区町村名は国土地理院地図の市区町村表を利用

地図の背景に国土地理院「淡色地図」（地理院タイル）を表示
https://maps.gsi.go.jp/development/ichiran.html
```

淡色地図のタイルは同梱せず、閲覧時にブラウザが国土地理院から直接取得する。
地図の右下に「国土地理院」の出典を表示している。

同梱: `data/raw/gsi/muni.js`（市区町村表）と `data/raw/gsi/revgeo.jsonl`
（古墳座標に対する逆ジオコーディング結果・2026-09-08 取得）。

全国 DEM そのものは再配布しない。リポジトリに入るのは次の三つだけである。

- `data/derived/terrain.jsonl` — 各古墳の座標に対する地形特徴量（標高・傾斜・方位・
  局所起伏・相対標高・地形の粗さ）。国土地理院の標高タイルを加工して作成
- `data/raw/gsi/revgeo.jsonl` — 座標に対する逆ジオコーディング結果
- `tests/fixtures/dem5a_15_29011_12939.png` — 検査用に 1 枚だけ置いた標高タイル
  （富士山頂を含む DEM5A z15）

標高タイルのローカルキャッシュ（`data/raw/gsi-cache/`、約 550 MB）は
`.gitignore` で除外している。

## 文化庁 / Agency for Cultural Affairs

```text
出典：文化庁「国指定文化財等データベース」
https://kunishitei.bunka.go.jp/bsys/index

画像は第三者が権利を有するため一切転載しない。
```

**V1.0 では取り込んでいない。** 人手スナップショットの手順だけを `data/raw/bunka/README.md` に置いた。
スナップショットは置かれておらず、出荷物に文化庁由来の値は 0 件である。

## 全国遺跡報告総覧 / 奈良文化財研究所

```text
https://sitereports.nabunken.go.jp/
外部リンクとしてのみ参照する。本文・PDF は取得も再配布もしない。
```

## 奈良女子大学「全国古墳データベース」

```text
https://zenkoku-kofun.nara-hgis.jp/zenkoku_kofun_home.html
学術研究目的に限定され、改変・再配布が禁止されている。
本プロジェクトはデータを取り込まず、参照 URL を記すにとどめる。
```

## ブラウザに配るライブラリ

| ライブラリ | 版 | ライセンス |
|---|---|---|
| MapLibre GL JS | 5.24.0 | BSD-3-Clause（`node_modules/maplibre-gl/LICENSE.txt`） |
| Next.js | 15.5.25 | MIT |
| React / React DOM | 19.2.8 | MIT |

版は 2026-09-15 に `node_modules` の `package.json` から読んだ。
