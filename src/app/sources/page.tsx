import type { Metadata } from "next";

import manifest from "../../../public/data/data-manifest.json";

export const metadata: Metadata = {
  title: "出典とデータの偏り | Kofun Atlas AI",
  description: "このアプリが使った公開データ、使わなかったデータ、そしてデータの偏り。",
};

const nf = new Intl.NumberFormat("ja-JP");

/*
 * 表の行はすべて実際の取り込みの状態に合わせる。構想書 §65 の表をそのまま写すと、
 * まだ取り込んでいない Wikidata と文化庁が「使っている」ように読める。
 */
const ROWS = [
  {
    source: "『日本歴史地名大系』施設・地点項目データセット（CODH 作成）",
    role: "古墳の名前・読み・位置",
    terms: "CC BY 4.0",
    status: "使用",
  },
  {
    source: "国土地理院「簡易逆ジオコーディング」・市区町村表",
    role: "都道府県・市区町村",
    terms: "国土地理院コンテンツ利用規約",
    status: "使用（結果を同梱）",
  },
  {
    source: "国土地理院「標高タイル」（DEM5A / 5B / 5C / 10B）",
    role: "地形の値",
    terms: "国土地理院コンテンツ利用規約",
    status: "加工した値だけを同梱",
  },
  {
    source: "国土地理院「淡色地図」",
    role: "地図の背景",
    terms: "国土地理院コンテンツ利用規約",
    status: "表示のみ",
  },
  {
    source: "Wikidata",
    role: "別名・時期などの補完（構想書の想定・V1.0 では使っていない）",
    terms: "CC0",
    status: "未取り込み（自動取得が robots.txt で禁止のため、人手の取得を待っている）",
  },
  {
    source: "文化庁「国指定文化財等データベース」",
    role: "指定文化財の属性（構想書の想定・V1.0 では使っていない）",
    terms: "文字情報は出典記載で利用可・画像は個別許諾",
    status: "未取り込み（人手の取得を待っている）",
  },
  {
    source: "全国遺跡報告総覧",
    role: "文献への案内（構想書の想定・V1.0 では使っていない）",
    terms: "資料ごとに確認",
    status: "未使用",
  },
  {
    source: "奈良女子大学「全国古墳データベース」",
    role: "参考",
    terms: "学術研究目的に限定・再配布禁止",
    status: "使わない（データを 1 件も取り込んでいない）",
  },
];

export default function SourcesPage() {
  const { counts } = manifest;
  return (
    <div className="wrap wide">
      <h1>出典とデータの偏り</h1>
      <p className="lede">このアプリが使った公開データと、使わなかったデータ、そして読み方の注意です。</p>

      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">データ</th>
              <th scope="col">役割</th>
              <th scope="col">利用条件</th>
              <th scope="col">このアプリでの扱い</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((r) => (
              <tr key={r.source}>
                <td>{r.source}</td>
                <td>{r.role}</td>
                <td>{r.terms}</td>
                <td>{r.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>表示している出典の文言</h2>
        <ul>
          {manifest.sources.map((s) => (
            <li key={s.id} className="note">
              {s.credit}／{s.license}（取得 {s.retrieved_at}）
            </li>
          ))}
        </ul>
      </div>

      <div className="card">
        <h2>データの偏り</h2>
        <ul>
          <li>
            収録は {nf.format(counts.records)} 件です。<strong>日本の古墳をすべて網羅するものではありません。</strong>たとえば箸墓古墳は載っていません。
          </li>
          <li>点の多い少ないは、その地域に古墳が多いかではなく、元データに載っているかを表します。</li>
          <li>
            墳形があるのは {nf.format(counts.with_mound_type)} 件、築造時期があるのは {nf.format(counts.with_chronology)}{" "}
            件です。空欄は「存在しない」ではなく「確認できない」の意味です。
          </li>
          <li>
            都道府県は座標から決めています。元データの県コードは {nf.format(counts.prefecture_corrected)} 件で座標と食い違っていました。
          </li>
          <li>地形の値は周囲 1,000 m を見て計算しています。島や海沿いの古墳では周囲の多くが水面で、その分を除いています。</li>
        </ul>
      </div>
    </div>
  );
}
