import manifest from "../../public/data/data-manifest.json";

const nf = new Intl.NumberFormat("ja-JP");

export default function Home() {
  const { counts, sources, version, stage } = manifest;

  return (
    <div className="wrap">
      <h1>Kofun Atlas AI</h1>
      <p className="lede">日本古墳 時空間・地形・AI 分析アトラス</p>

      <div className="card">
        <h2>採録範囲</h2>
        <p>
          本アプリは公開・再利用可能な資料を統合したものであり、
          <strong>日本国内の全古墳を網羅するものではありません。</strong>
        </p>
        <p className="note">
          現在の収録件数 {nf.format(counts.records)} 件（
          {sources[0].source_version} 版の
          {sources[0].credit}
          から {nf.format(counts.geoshape_rows)} 行を取り込み、同一古墳の重複{" "}
          {counts.merged_duplicate_rows} 行を統合）。データ版 {version}。
        </p>
      </div>

      <div className="card">
        <h2>いまの状態（{stage}）</h2>
        <p className="note">
          このアプリは段階的に作っています。埋まっていない欄は推測で埋めず、
          空のまま置いています。
        </p>
        <ul>
          <li>座標あり: {nf.format(counts.with_coordinates)} 件</li>
          <li>
            都道府県・市区町村の確定: {nf.format(counts.with_prefecture)} 件（L1
            で座標から確定します）
          </li>
          <li>墳形あり: {nf.format(counts.with_mound_type)} 件</li>
          <li>築造時期あり: {nf.format(counts.with_chronology)} 件</li>
        </ul>
        <p className="note">
          地図・類似検索・AI 分析はこれから実装します。
        </p>
      </div>

      <div className="card">
        <h2>出典</h2>
        <ul>
          {sources.map((s) => (
            <li key={s.id} className="note">
              {s.credit}／{s.license}（取得 {s.retrieved_at}）
            </li>
          ))}
        </ul>
        <p className="note">
          地形の値は国土地理院の標高データを加工して作成します。
        </p>
      </div>
    </div>
  );
}
