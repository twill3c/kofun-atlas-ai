"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  ACCENT,
  MUTED,
  METRICS,
  PAD,
  RAMP,
  SINGLE,
  VIEW,
  chooseRadius,
  classOf,
  fromUser,
  quantileBreaks,
  selectInRect,
  toUser,
  type ExploreData,
  type MetricKey,
  type Rect,
} from "@/lib/explore";

const DATA_URL = "/data/explore.json";
const TABLE_LIMIT = 100;
const nf = new Intl.NumberFormat("ja-JP");

type Brush = { ux0: number; uy0: number; ux1: number; uy1: number };

function fmt(v: number | null, digits: number, unit: string) {
  if (v === null) return "値なし";
  return `${v.toLocaleString("ja-JP", { minimumFractionDigits: digits, maximumFractionDigits: digits })}${unit ? ` ${unit}` : ""}`;
}

export default function ExploreView() {
  const [data, setData] = useState<ExploreData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [metric, setMetric] = useState<MetricKey | "">("elevation_m");
  const [pref, setPref] = useState("");
  const [brush, setBrush] = useState<Brush | null>(null);
  const [dragging, setDragging] = useState(false);
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    fetch(DATA_URL)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`探索用データを読めない(HTTP ${r.status})`))))
      .then((d: ExploreData) => setData(d))
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  const userXY = useMemo(() => {
    if (!data) return [] as [number, number][];
    return data.xy.map(([x, y]) => toUser(x, y));
  }, [data]);

  const { radius, fractions } = useMemo(() => chooseRadius(userXY), [userXY]);

  const prefectures = useMemo(() => {
    if (!data) return [];
    const counts = new Map<string, number>();
    for (const p of data.pref) if (p) counts.set(p, (counts.get(p) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [data]);

  const scale = useMemo(() => {
    if (!data || !metric) return null;
    const values = data.metrics[metric];
    const breaks = quantileBreaks(values);
    const counts = [0, 0, 0, 0, 0];
    const sorted = values.filter((v): v is number => v !== null).sort((a, b) => a - b);
    for (const v of values) {
      const c = classOf(v, breaks);
      if (c !== null) counts[c]++;
    }
    return { breaks, counts, min: sorted[0], max: sorted[sorted.length - 1], values };
  }, [data, metric]);

  // 選択: 範囲選択(二次元配置の正規化座標)と県の強調の積
  const selected = useMemo(() => {
    if (!data) return null;
    let set: Set<number> | null = null;
    if (brush) {
      const [ax, ay] = fromUser(Math.min(brush.ux0, brush.ux1), Math.max(brush.uy0, brush.uy1));
      const [bx, by] = fromUser(Math.max(brush.ux0, brush.ux1), Math.min(brush.uy0, brush.uy1));
      const rect: Rect = { x0: ax, x1: bx, y0: ay, y1: by };
      set = new Set(selectInRect(data.xy, rect));
    }
    if (pref) {
      const inPref = new Set(data.pref.flatMap((p, i) => (p === pref ? [i] : [])));
      set = set ? new Set([...set].filter((i) => inPref.has(i))) : inPref;
    }
    return set;
  }, [data, brush, pref]);

  const colorOf = (i: number) => {
    if (selected && !selected.has(i)) return MUTED;
    if (!scale) return SINGLE;
    const c = classOf(scale.values[i], scale.breaks);
    return c === null ? MUTED : RAMP[c];
  };

  // 日本の縮小図(経緯度を正距円筒に。緯度で経度を縮める)
  const inset = useMemo(() => {
    if (!data) return null;
    const lons = data.lonlat.map((p) => p[0]);
    const lats = data.lonlat.map((p) => p[1]);
    const [minLon, maxLon, minLat, maxLat] = [Math.min(...lons), Math.max(...lons), Math.min(...lats), Math.max(...lats)];
    const k = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180);
    const w = (maxLon - minLon) * k;
    const h = maxLat - minLat;
    const size = 300;
    const pad = 8;
    const s = (size - 2 * pad) / Math.max(w, h);
    const width = w * s + 2 * pad;
    const height = h * s + 2 * pad;
    const pts = data.lonlat.map(([lon, lat]) => [pad + (lon - minLon) * k * s, pad + (maxLat - lat) * s] as [number, number]);
    return { width, height, pts };
  }, [data]);

  const toSvgPoint = (e: React.PointerEvent) => {
    const svg = svgRef.current;
    if (!svg) return null;
    const ctm = svg.getScreenCTM();
    if (!ctm) return null;
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    return [Math.min(VIEW, Math.max(0, p.x)), Math.min(VIEW, Math.max(0, p.y))] as [number, number];
  };

  const nearest = (ux: number, uy: number) => {
    let best = -1;
    let bestD = 14 * 14; // 描画単位で 14 以内の最寄り点だけを拾う
    userXY.forEach(([x, y], i) => {
      const d = (x - ux) ** 2 + (y - uy) ** 2;
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    });
    return best >= 0 ? best : null;
  };

  const tableRows = useMemo(() => {
    if (!data || !selected) return [];
    return [...selected].sort((a, b) => data.name[a].localeCompare(data.name[b], "ja")).slice(0, TABLE_LIMIT);
  }, [data, selected]);

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!data || !inset) return <p className="note" role="status">読み込み中…</p>;

  const metricDef = METRICS.find((m) => m.key === metric);

  return (
    <div className="explore">
      <div className="filter-row">
        <label className="field">
          <span>色で表す量</span>
          <select value={metric} onChange={(e) => setMetric(e.target.value as MetricKey | "")}>
            <option value="">なし(単色)</option>
            {METRICS.map((m) => (
              <option key={m.key} value={m.key}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>都道府県を強調</span>
          <select value={pref} onChange={(e) => setPref(e.target.value)}>
            <option value="">なし</option>
            {prefectures.map(([p, n]) => (
              <option key={p} value={p}>
                {p}({n})
              </option>
            ))}
          </select>
        </label>
        {brush && (
          <button type="button" className="secondary" onClick={() => setBrush(null)}>
            範囲選択を外す
          </button>
        )}
      </div>

      {scale && metricDef && (
        <div className="legend" aria-label={`${metricDef.label}の凡例`}>
          <span className="legend-title">{metricDef.label}(5 つの分位クラス)</span>
          <ol className="legend-steps">
            {RAMP.map((color, c) => {
              const lo = c === 0 ? scale.min : scale.breaks[c - 1];
              const hi = c === RAMP.length - 1 ? scale.max : scale.breaks[c];
              return (
                <li key={color}>
                  <span className="swatch" style={{ background: color }} aria-hidden="true" />
                  {fmt(lo, metricDef.digits, metricDef.unit)} 〜 {fmt(hi, metricDef.digits, metricDef.unit)}
                  <span className="note">({nf.format(scale.counts[c])} 件)</span>
                </li>
              );
            })}
          </ol>
          <p className="note">同じ値が境界に並ぶので、各クラスの件数はちょうど 5 等分にはなりません。</p>
        </div>
      )}

      <div className="explore-figures">
        <figure className="scatter">
          <svg
            ref={svgRef}
            viewBox={`0 0 ${VIEW} ${VIEW}`}
            data-view={VIEW}
            data-pad={PAD}
            data-radius={radius}
            role="img"
            aria-label="立地の二次元配置。近い点どうしは立地が似ている。ドラッグで範囲を選べる"
            onPointerDown={(e) => {
              const p = toSvgPoint(e);
              if (!p) return;
              (e.target as Element).setPointerCapture?.(e.pointerId);
              setDragging(true);
              setBrush({ ux0: p[0], uy0: p[1], ux1: p[0], uy1: p[1] });
            }}
            onPointerMove={(e) => {
              const p = toSvgPoint(e);
              if (!p) return;
              if (dragging) setBrush((b) => (b ? { ...b, ux1: p[0], uy1: p[1] } : b));
              else setHover(nearest(p[0], p[1]));
            }}
            onPointerUp={() => {
              setDragging(false);
              setBrush((b) => (b && Math.abs(b.ux1 - b.ux0) < 2 && Math.abs(b.uy1 - b.uy0) < 2 ? null : b));
            }}
            onPointerLeave={() => setHover(null)}
          >
            <rect x={0} y={0} width={VIEW} height={VIEW} className="plot-surface" />
            <g className="points">
              {userXY.map(([x, y], i) => (
                <circle key={data.ids[i]} data-i={i} cx={x.toFixed(2)} cy={y.toFixed(2)} r={radius} fill={colorOf(i)} />
              ))}
            </g>
            {hover !== null && (
              <circle
                className="hover-ring"
                cx={userXY[hover][0].toFixed(2)}
                cy={userXY[hover][1].toFixed(2)}
                r={radius + 3}
                fill="none"
              />
            )}
            {brush && (
              <rect
                className="brush"
                x={Math.min(brush.ux0, brush.ux1)}
                y={Math.min(brush.uy0, brush.uy1)}
                width={Math.abs(brush.ux1 - brush.ux0)}
                height={Math.abs(brush.uy1 - brush.uy0)}
              />
            )}
          </svg>
          {hover !== null && (
            <div className="tooltip" role="status">
              <strong>{data.name[hover]}</strong>
              <span className="note">{data.pref[hover] ?? "県不明"}</span>
              {METRICS.map((m) => (
                <span key={m.key} className="note">
                  {m.label} {fmt(data.metrics[m.key][hover], m.digits, m.unit)}
                </span>
              ))}
            </div>
          )}
          <figcaption className="note">
            点の半径 {radius}(重なりの割合: {Object.entries(fractions)
              .map(([r, f]) => `半径 ${r}: ${(f * 100).toFixed(1)}%`)
              .join(" / ")}
            )。t-SNE が保つのは近所の並びだけで、離れた点どうしの距離は読み取れません。
          </figcaption>
        </figure>

        <figure className="inset">
          <svg
            viewBox={`0 0 ${inset.width.toFixed(2)} ${inset.height.toFixed(2)}`}
            role="img"
            aria-label="同じ古墳を実際の位置で並べた日本の縮小図"
          >
            <rect x={0} y={0} width={inset.width.toFixed(2)} height={inset.height.toFixed(2)} className="plot-surface" />
            {inset.pts.map(([x, y], i) => (
              <circle key={data.ids[i]} cx={x.toFixed(2)} cy={y.toFixed(2)} r={1.4} fill={colorOf(i)} />
            ))}
          </svg>
          <figcaption className="note">同じ色で、実際の場所に並べた図です。</figcaption>
        </figure>
      </div>

      <section aria-labelledby="selection-title">
        <h2 id="selection-title">選んだ古墳</h2>
        {selected === null ? (
          <p className="note">図をドラッグして範囲を選ぶか、都道府県を選ぶと、ここに一覧が出ます。</p>
        ) : (
          <>
            <p className="note" aria-live="polite">
              {nf.format(selected.size)} 件
              {selected.size > TABLE_LIMIT && `(先頭 ${TABLE_LIMIT} 件を名前順に表示)`}
            </p>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">名前</th>
                    <th scope="col">都道府県</th>
                    {METRICS.map((m) => (
                      <th key={m.key} scope="col" className="num">
                        {m.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {tableRows.map((i) => (
                    <tr key={data.ids[i]}>
                      <td>{data.name[i]}</td>
                      <td>{data.pref[i] ?? "県不明"}</td>
                      {METRICS.map((m) => (
                        <td key={m.key} className="num">
                          {fmt(data.metrics[m.key][i], m.digits, m.unit)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      {/* 強調色は範囲選択の枠にだけ使う。点の色は量の塗りか灰のどちらか */}
      <style>{`.explore .brush { fill: ${ACCENT}22; stroke: ${ACCENT}; stroke-width: 1.5; }`}</style>
    </div>
  );
}
