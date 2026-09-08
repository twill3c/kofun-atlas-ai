# Wikidata スナップショットの取り方（人手）

## なぜ自動取得しないか

`https://query.wikidata.org/robots.txt` は次のとおりで、SPARQL エンドポイントは
自動巡回の対象外である（2026-09-08 実測）。

```text
User-agent: *
Disallow: /sparql
Disallow: /bigdata
```

`https://www.wikidata.org/robots.txt` も `User-agent: *` に対し `/w/` と `/api/` を
Disallow しているので、Action API・`Special:EntityData` も同じく使わない。

したがって Wikidata は **文化庁 CSV と同じ人手スナップショット方式**にする。
CI からもスクリプトからも取得しない（SPEC §3.3）。

## 手順

1. ブラウザで <https://query.wikidata.org/> を開く
2. 下のクエリを貼って実行する
3. 結果を JSON で保存し、`data/raw/wikidata/YYYY-MM-DD/kofun.json` に置く
4. `python scripts/import_wikidata.py`（L1 で用意する）を実行する

## クエリ

```sparql
SELECT ?item ?itemLabel ?itemAltLabel ?coord ?inception ?admin ?adminLabel
       ?heritage ?heritageLabel ?commons
WHERE {
  ?item wdt:P31/wdt:P279* wd:Q1141225 .
  OPTIONAL { ?item wdt:P625 ?coord . }
  OPTIONAL { ?item wdt:P571 ?inception . }
  OPTIONAL { ?item wdt:P131 ?admin . }
  OPTIONAL { ?item wdt:P1435 ?heritage . }
  OPTIONAL { ?item wdt:P373 ?commons . }

  SERVICE wikibase:label {
    bd:serviceParam wikibase:language "ja,en".
  }
}
ORDER BY ?item
```

件数が多くて画面が返さない場合は `LIMIT 500 OFFSET n` で分けて取り、
同じ日付のディレクトリに `kofun-0000.json` のように連番で置く。

## ライセンス

Wikidata の構造化データは **CC0**。
<https://www.wikidata.org/wiki/Wikidata:Licensing>
