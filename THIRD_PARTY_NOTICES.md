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

## 国土地理院 / Geospatial Information Authority of Japan

```text
出典：国土地理院ウェブサイト
https://www.gsi.go.jp/

国土地理院の標高データを加工して作成
（elevation / slope / relief などの地形特徴量）

逆ジオコーディングに国土地理院の
「簡易逆ジオコーディングサービス」を利用
```

全国 DEM そのものは再配布しない。リポジトリに入るのは派生した特徴量と、
検査用に 1 枚だけ置いた標高タイル
（`tests/fixtures/dem5a_15_29011_12939.png`、富士山頂を含む DEM5A z15 タイル）である。

## 文化庁 / Agency for Cultural Affairs

```text
出典：文化庁「国指定文化財等データベース」
https://kunishitei.bunka.go.jp/bsys/index

文字情報を出典表示のうえ利用している。
画像は第三者が権利を有するため一切転載しない。
```

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
