import type { Metadata } from "next";

import { METRICS, median } from "@/lib/explore";
import explore from "../../../public/data/explore.json";

export const metadata: Metadata = {
  title: "都道府県の比較 | Kofun Atlas AI",
  description: "収録した古墳の件数と、置かれた場所の地形の中央値を都道府県ごとに並べた表。",
};

const nf = new Intl.NumberFormat("ja-JP");

type Row = { pref: string; count: number; medians: (number | null)[] };

function buildRows(): Row[] {
  const groups = new Map<string, number[]>();
  explore.pref.forEach((p, i) => {
    if (!p) return;
    const list = groups.get(p);
    if (list) list.push(i);
    else groups.set(p, [i]);
  });
  const metrics = explore.metrics as Record<string, (number | null)[]>;
  return [...groups.entries()]
    .map(([pref, members]) => ({
      pref,
      count: members.length,
      medians: METRICS.map((m) => median(members.map((i) => metrics[m.key][i]))),
    }))
    .sort((a, b) => b.count - a.count || a.pref.localeCompare(b.pref, "ja"));
}

export default function ComparePage() {
  const rows = buildRows();
  return (
    <div className="wrap wide">
      <h1>都道府県の比較</h1>
      <p className="lede">収録した古墳の件数と、置かれた場所の地形の中央値を都道府県ごとに並べました。</p>
      <p className="note notice">
        <strong>件数は、このアプリが収録した件数であって、その県に実在する古墳の数ではありません。</strong>元データ（『日本歴史地名大系』の見出し項目）に載っているかどうかで決まります。構想書は墳形や時期の構成比の比較も挙げていますが、それを示す公開データが 1 件も無いので出していません。
      </p>
      <div className="table-scroll">
        <table className="data-table">
          <caption className="note">{rows.length} 都道府県・件数の多い順</caption>
          <thead>
            <tr>
              <th scope="col">都道府県</th>
              <th scope="col" className="num">
                収録件数
              </th>
              {METRICS.map((m) => (
                <th key={m.key} scope="col" className="num">
                  {m.label}の中央値
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.pref}>
                <td>{row.pref}</td>
                <td className="num">{nf.format(row.count)}</td>
                {row.medians.map((v, j) => (
                  <td key={METRICS[j].key} className="num">
                    {v === null
                      ? "値なし"
                      : `${v.toLocaleString("ja-JP", {
                          minimumFractionDigits: METRICS[j].digits,
                          maximumFractionDigits: METRICS[j].digits,
                        })}${METRICS[j].unit ? ` ${METRICS[j].unit}` : ""}`}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="note">
        中央値は、値のある件を小さい順に並べた真ん中の値です（偶数個なら真ん中二つの平均）。件数の少ない県の中央値は、数件の古墳の立地で大きく動きます。
      </p>
    </div>
  );
}
