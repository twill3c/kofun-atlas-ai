"use client";

import maplibregl, { type Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { shardOf } from "@/lib/shard";
import { topK } from "@/lib/similarity";

const GSI_PALE = "https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png";
const POINTS_URL = "/data/kofun-points.geojson";
const EMBEDDINGS_URL = "/data/embeddings.json";
const DETAILS_URL = (id: string) => `/data/kofun-details/${shardOf(id)}.json`;

/** 日本全体が入る初期表示。 */
const INITIAL = { center: [137.5, 36.4] as [number, number], zoom: 4.3 };

/* 色は二つだけ使う。点の色を属性で塗り分けない —— 墳形・時期はデータが 0 件で、
 * 塗り分ける根拠になる属性がそもそも無い(SPEC §3.7)。 */
const POINT = "#c8813a";
const HIGHLIGHT = "#1f6feb";
const SIMILAR_K = 10;
const SEARCH_LIMIT = 30;

type PointProps = {
  id: string;
  name: string;
  kana: string | null;
  pref: string | null;
  muni: string | null;
};
type PointFeature = {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: PointProps;
};
type Detail = {
  id: string;
  name: string;
  name_kana: string | null;
  prefecture: string | null;
  municipality: string | null;
  lat: number;
  lon: number;
  is_group_name: boolean;
  terrain: Record<string, number | null>;
  sources: { source: string; credit: string; license: string; retrieved_at: string }[];
};
type Similar = { id: string; name: string; pref: string | null; muni: string | null; score: number; rank: number };

const TERRAIN_LABELS: [key: string, label: string, unit: string, digits: number][] = [
  ["elevation_m", "標高", "m", 1],
  ["slope_deg", "傾斜", "度", 1],
  ["aspect_deg", "斜面の向き(下り方向)", "度", 0],
  ["local_relief_250m", "起伏(半径 250 m)", "m", 1],
  ["local_relief_500m", "起伏(半径 500 m)", "m", 1],
  ["local_relief_1000m", "起伏(半径 1,000 m)", "m", 1],
  ["relative_elevation_500m", "周囲との高さの差(半径 500 m)", "m", 1],
  ["openness_500m", "周囲より高い度合い(0〜1)", "", 2],
];

function fmt(value: number | null | undefined, digits: number, unit: string): string {
  if (value === null || value === undefined) return "値なし";
  return `${value.toLocaleString("ja-JP", { maximumFractionDigits: digits, minimumFractionDigits: digits })}${unit ? ` ${unit}` : ""}`;
}

export default function KofunMap({ prefectures }: { prefectures: string[] }) {
  const container = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const featuresRef = useRef<PointFeature[]>([]);
  const indexRef = useRef<Map<string, number>>(new Map());
  const vectorsRef = useRef<number[][] | null>(null);

  const [loaded, setLoaded] = useState(false);
  const [total, setTotal] = useState<number | null>(null);
  const [pref, setPref] = useState("");
  const [query, setQuery] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [similar, setSimilar] = useState<Similar[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // --- 地図の初期化 ---------------------------------------------------------
  useEffect(() => {
    if (!container.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      style: {
        version: 8,
        sources: {
          gsi: {
            type: "raster",
            tiles: [GSI_PALE],
            tileSize: 256,
            maxzoom: 18,
            attribution:
              '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noreferrer">国土地理院</a>',
          },
        },
        layers: [
          // 背景を必ず置く。無いとタイル未着の場所でページの背景色が地図に透ける
          // (jinja-origin-atlas-ai で目視でのみ見つかった型)。
          { id: "bg", type: "background", paint: { "background-color": "#dfe6ea" } },
          { id: "gsi", type: "raster", source: "gsi" },
        ],
      },
      center: INITIAL.center,
      zoom: INITIAL.zoom,
      attributionControl: false,
    });
    mapRef.current = map;
    // 検品の口。WebGL の中身は DOM から見えないので、実ブラウザ検品が map API で数える(HC-138)。
    (window as unknown as { __kofunMap?: MapLibreMap }).__kofunMap = map;

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.AttributionControl({ compact: false }), "bottom-right");
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: "metric" }), "bottom-left");

    map.on("load", () => {
      map.resize();
      map.addSource("kofun", {
        type: "geojson",
        data: POINTS_URL,
        attribution:
          '『日本歴史地名大系』施設・地点項目データセット(<a href="https://doi.org/10.20676/00000456" target="_blank" rel="noreferrer">CODH</a>) CC BY 4.0',
      });
      map.addSource("similar", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addSource("selected", { type: "geojson", data: { type: "FeatureCollection", features: [] } });

      map.addLayer({
        id: "kofun-points",
        type: "circle",
        source: "kofun",
        paint: {
          "circle-color": POINT,
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 2.2, 8, 3.5, 13, 6],
          "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 4, 0.4, 10, 1],
          "circle-stroke-color": "#3b2a18",
        },
      });
      map.addLayer({
        id: "similar-points",
        type: "circle",
        source: "similar",
        paint: {
          "circle-color": HIGHLIGHT,
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 4.5, 10, 7],
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#ffffff",
        },
      });
      map.addLayer({
        id: "selected-point",
        type: "circle",
        source: "selected",
        paint: {
          "circle-color": "#ffffff",
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 6, 10, 9],
          "circle-stroke-width": 3,
          "circle-stroke-color": "#111111",
        },
      });

      for (const layer of ["kofun-points", "similar-points"]) {
        map.on("click", layer, (e) => {
          const id = e.features?.[0]?.properties?.id as string | undefined;
          if (id) void selectRef.current(id, false);
        });
        map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
        map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
      }
      setLoaded(true);
    });
    map.on("error", (e) => setError(String(e.error?.message ?? "地図の読み込みに失敗しました")));

    // 器の寸法が変わってもキャンバスは追随しない。追随を明示的に書く。
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(container.current);

    fetch(POINTS_URL)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`古墳の点を読めない(HTTP ${r.status})`))))
      .then((fc: { features: PointFeature[] }) => {
        featuresRef.current = fc.features;
        indexRef.current = new Map(fc.features.map((f, i) => [f.properties.id, i]));
        setTotal(fc.features.length);
      })
      .catch((e) => setError(String(e.message ?? e)));

    return () => {
      ro.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // --- 都道府県の絞り込み ---------------------------------------------------
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    map.setFilter("kofun-points", pref ? ["==", ["get", "pref"], pref] : null);
  }, [pref, loaded]);

  const shown = useMemo(() => {
    if (total === null) return null;
    return pref ? featuresRef.current.filter((f) => f.properties.pref === pref).length : total;
  }, [pref, total]);

  // --- 名称検索(地図を使えない人のための一覧も兼ねる) --------------------
  const results = useMemo(() => {
    const q = query.trim();
    if (!q || total === null) return [];
    const hits: PointFeature[] = [];
    for (const f of featuresRef.current) {
      if (pref && f.properties.pref !== pref) continue;
      const p = f.properties;
      if (p.name.includes(q) || (p.kana ?? "").includes(q) || (p.muni ?? "").includes(q)) {
        hits.push(f);
        if (hits.length >= SEARCH_LIMIT) break;
      }
    }
    return hits;
  }, [query, pref, total]);

  // --- 選択と詳細 -----------------------------------------------------------
  const select = useCallback(async (id: string, fly: boolean) => {
    const map = mapRef.current;
    const i = indexRef.current.get(id);
    if (i === undefined) return;
    const feature = featuresRef.current[i];
    setError(null);
    setSimilar(null);
    setBusy("詳細を読み込み中…");
    try {
      const r = await fetch(DETAILS_URL(id));
      if (!r.ok) throw new Error(`詳細を読めない(HTTP ${r.status})`);
      const shard: Record<string, Detail> = await r.json();
      const d = shard[id];
      if (!d) throw new Error(`詳細に ${id} が無い`);
      setDetail(d);
      if (map) {
        (map.getSource("selected") as maplibregl.GeoJSONSource).setData({
          type: "FeatureCollection",
          features: [feature],
        });
        (map.getSource("similar") as maplibregl.GeoJSONSource).setData({
          type: "FeatureCollection",
          features: [],
        });
        if (fly) map.flyTo({ center: feature.geometry.coordinates, zoom: Math.max(map.getZoom(), 10) });
      }
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  }, []);
  const selectRef = useRef(select);
  selectRef.current = select;

  const findSimilar = useCallback(async () => {
    if (!detail) return;
    const map = mapRef.current;
    setBusy("立地の似た古墳を探しています…");
    try {
      if (!vectorsRef.current) {
        const r = await fetch(EMBEDDINGS_URL);
        if (!r.ok) throw new Error(`埋め込みを読めない(HTTP ${r.status})`);
        const payload: { ids: string[]; embeddings: number[][] } = await r.json();
        // 埋め込みと点の並びが同じであることを確かめてから使う(境界をまたぐ契約)。
        const same =
          payload.ids.length === featuresRef.current.length &&
          payload.ids.every((id, i) => featuresRef.current[i].properties.id === id);
        if (!same) throw new Error("埋め込みと古墳の並びが一致しない");
        vectorsRef.current = payload.embeddings;
      }
      const q = indexRef.current.get(detail.id);
      if (q === undefined) return;
      const hits = topK(vectorsRef.current, q, SIMILAR_K).map((n, rank) => {
        const p = featuresRef.current[n.index].properties;
        return { id: p.id, name: p.name, pref: p.pref, muni: p.muni, score: n.score, rank: rank + 1 };
      });
      setSimilar(hits);
      if (map) {
        const hitFeatures = hits.map((h) => featuresRef.current[indexRef.current.get(h.id)!]);
        (map.getSource("similar") as maplibregl.GeoJSONSource).setData({
          type: "FeatureCollection",
          features: hitFeatures,
        });
        // **強調したものが見える範囲へ寄せる。** 立地で選ぶので、似た古墳は全国に散るのが普通である。
        // 寄せないと、対象へ zoom 10 で寄ったままの地図に強調が 1 件も入らない
        // (実測: 江別古墳群で視野内 0/10)。対象も一緒に収める。
        const coords = [featuresRef.current[q].geometry.coordinates, ...hitFeatures.map((f) => f.geometry.coordinates)];
        const xs = coords.map((c) => c[0]);
        const ys = coords.map((c) => c[1]);
        map.fitBounds(
          [
            [Math.min(...xs), Math.min(...ys)],
            [Math.max(...xs), Math.max(...ys)],
          ],
          { padding: 48, maxZoom: 11, duration: 600 },
        );
      }
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  }, [detail]);

  return (
    <div className="map-layout">
      <aside className="map-panel" aria-label="絞り込みと検索">
        <label className="field">
          <span>都道府県</span>
          <select value={pref} onChange={(e) => setPref(e.target.value)}>
            <option value="">すべて</option>
            {prefectures.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <p className="note" aria-live="polite">
          表示中: {shown === null ? "読み込み中…" : `${shown.toLocaleString("ja-JP")} 件`}
          {pref && total !== null && ` / 全 ${total.toLocaleString("ja-JP")} 件`}
        </p>

        <label className="field">
          <span>名前・読み・市区町村で探す</span>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="例: 大塚、はしはか、桜井市"
          />
        </label>
        {query.trim() && (
          <ul className="result-list" aria-label="検索結果">
            {results.length === 0 && <li className="note">見つかりません</li>}
            {results.map((f) => (
              <li key={f.properties.id}>
                <button type="button" onClick={() => void select(f.properties.id, true)}>
                  {f.properties.name}
                  {/* 所在地は二行目に置く。空白で区切ると和文の中の空白になり、狭い幅で途中から折り返す */}
                  <span className="note sub">
                    {f.properties.pref}
                    {f.properties.muni}
                  </span>
                </button>
              </li>
            ))}
            {results.length >= SEARCH_LIMIT && (
              <li className="note">先頭 {SEARCH_LIMIT} 件だけを表示しています</li>
            )}
          </ul>
        )}

        <p className="note">
          点の色で墳形や時期を塗り分けていないのは、それを示す公開データが無いためです(1 件も無い)。
        </p>
      </aside>

      <div className="map-main">
        <div
          ref={container}
          className="map-canvas"
          role="application"
          aria-label="古墳の分布地図。キーボードでは矢印キーで移動、+ / - で拡大縮小できます。一覧から選ぶには左の検索を使ってください。"
          tabIndex={0}
        />
        {/* 出典は JavaScript に依存させない。地図が読めなくても表示される */}
        <p className="note map-credit">
          古墳の位置: 『日本歴史地名大系』施設・地点項目データセット(CODH作成)CC BY 4.0 ／ 背景地図・標高:
          国土地理院
        </p>
        {busy && (
          <p className="note" role="status">
            {busy}
          </p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        {detail && (
          <section className="card detail" aria-labelledby="detail-title">
            <h2 id="detail-title">{detail.name}</h2>
            <p className="note">
              {detail.name_kana ?? "読みなし"} ／ {detail.prefecture ?? "県不明"}
              {detail.municipality ?? ""} ／ 緯度 {detail.lat.toFixed(5)}・経度 {detail.lon.toFixed(5)}
              {detail.is_group_name && " ／ 名前に「群」を含む"}
            </p>

            <h3>地形(国土地理院の標高データから算出)</h3>
            <dl className="terrain">
              {TERRAIN_LABELS.map(([key, label, unit, digits]) => (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>{fmt(detail.terrain[key], digits, unit)}</dd>
                </div>
              ))}
            </dl>
            {(detail.terrain.dem_missing_ratio ?? 0) > 0.2 && (
              <p className="note">
                周囲 1,000 m のうち {Math.round((detail.terrain.dem_missing_ratio ?? 0) * 100)}%
                は水面などで標高がありません。起伏の値はその分を除いて計算しています。
              </p>
            )}

            <h3>公開データに無いもの</h3>
            {/* 和文の本文は行の途中で改行しない。JSX は改行と字下げを空白一つに畳む */}
            <p className="note">
              墳形・墳丘長・築造時期・埋葬施設・出土品は、再配布できる公開データでは埋まっていません。空欄は「確認できない」の意味で、「存在しない」ではありません。
            </p>

            <button type="button" className="primary" onClick={() => void findSimilar()} disabled={!!busy}>
              立地の似た古墳を探す
            </button>
            {similar && (
              <>
                <h3>立地の似た古墳(上位 {SIMILAR_K} 件)</h3>
                <p className="note">
                  地形とまわりの古墳の多さだけで比べています。古墳そのもの(形・時期・系統)が似ているという意味ではありません。類似度の値どうしの差は小さいので、値より順位を見てください。
                </p>
                <ol className="similar-list">
                  {similar.map((s) => (
                    <li key={s.id}>
                      <button type="button" onClick={() => void select(s.id, true)}>
                        {s.rank}. {s.name}
                        <span className="note sub">
                          {s.pref}
                          {s.muni} ／ 類似度 {s.score.toFixed(3)}
                        </span>
                      </button>
                    </li>
                  ))}
                </ol>
              </>
            )}

            <h3>出典</h3>
            <ul className="note">
              {detail.sources.map((s) => (
                <li key={s.source}>
                  {s.credit}({s.license}・取得 {s.retrieved_at})
                </li>
              ))}
              <li>地形は国土地理院の標高データを加工して作成</li>
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
