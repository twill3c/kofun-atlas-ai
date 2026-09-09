import manifest from "../../public/data/data-manifest.json";

const nf = new Intl.NumberFormat("ja-JP");

// 段階ごとに欄が増えるので、形は緩く受ける。数値の正本は manifest 側。
const prefectures = manifest.prefectures as Record<string, number>;

export default function Home() {
  const { counts, sources, version, stage } = manifest;
  const geoshape = sources.find((s) => s.id === "geoshape");
  const topPrefectures = Object.entries(prefectures)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);

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
          {geoshape?.source_version} 版の {geoshape?.credit} から{" "}
          {nf.format(counts.geoshape_rows)} 行を取り込み、同一古墳の重複{" "}
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
            都道府県・市区町村の確定: {nf.format(counts.with_prefecture)} 件
            {counts.without_muni_cd > 0 && (
              <>（未確定 {nf.format(counts.without_muni_cd)} 件）</>
            )}
          </li>
          <li>
            地形（標高・傾斜・起伏）: {nf.format(counts.with_elevation)} 件
          </li>
          <li>墳形あり: {nf.format(counts.with_mound_type)} 件</li>
          <li>築造時期あり: {nf.format(counts.with_chronology)} 件</li>
        </ul>
        <p className="note">地図・類似検索・AI 分析はこれから実装します。</p>
      </div>

      {counts.with_elevation > 0 && (
        <div className="card">
          <h2>地形</h2>
          <p className="note">
            国土地理院の標高タイルから、各古墳の周囲 ±1,000 m を見て
            標高・傾斜・方位・局所起伏（250 / 500 / 1,000 m）・相対標高・
            地形の粗さを算出しています。
          </p>
          <p className="note">
            水面には標高がないので、そこは<strong>空のまま</strong>にしてあります。
            0 で埋めると「標高 0 m の崖」が生まれ、起伏が実際より大きく出ます。
            島や海沿いの古墳では周囲の多くが水面になります。
          </p>
        </div>
      )}

      {topPrefectures.length > 0 && (
        <div className="card">
          <h2>都道府県の分布（上位 8）</h2>
          <ul>
            {topPrefectures.map(([name, count]) => (
              <li key={name}>
                {name} {nf.format(count)} 件
              </li>
            ))}
          </ul>
          <p className="note">
            都道府県は、元データの県名・県コードではなく
            <strong>座標から国土地理院の逆ジオコーダで確定</strong>
            しています。元データの県コードを逆ジオコーダが覆した件数は{" "}
            {nf.format(counts.prefecture_corrected)} 件です。
          </p>
        </div>
      )}

      {counts.with_embedding > 0 && (
        <div className="card">
          <h2>立地の類似度（AI）</h2>
          <p className="note">
            各古墳の<strong>置かれた場所</strong>（地形と、まわりにどれだけ古墳が
            あるか）を {nf.format(counts.with_embedding)} 件ぶん 8 次元のベクトルに
            変換しています。似た立地の古墳を探すのに使います。
          </p>
          <p className="note">
            <strong>
              これは古墳そのものの特徴ではありません。
            </strong>
            墳形・墳丘長・築造時期・出土品は、再配布できる公開データでは 1 件も
            埋まっていないためです。考古学上の系統関係や編年を示すものではありません。
          </p>
          <p className="note">
            立地だけを見ているので、<strong>地形の似た別の地域</strong>の古墳が
            近くに出ます。これは仕様です。
          </p>
        </div>
      )}

      {manifest.projection && (
        <div className="card">
          <h2>立地の地図（二次元配置）</h2>
          <p className="note">
            8 次元の立地ベクトルを {manifest.projection.method} で 2
            次元に落として、{nf.format(manifest.projection.records)}{" "}
            件を一枚に並べられるようにしました。近くにある点どうしは、立地が
            似ています。近さの保存度（trustworthiness）は{" "}
            {manifest.projection.trustworthiness.toFixed(4)} です。
          </p>
          <p className="note">
            測っているのは<strong>近所の保たれ方だけ</strong>です。図全体の
            大きな配置（離れた点どうしの距離）がどれだけ正しいかは測っていないので、
            そこは読み取らないでください。
          </p>
        </div>
      )}

      <div className="card">
        <h2>群に切れなかったこと</h2>
        <p className="note">
          立地でグループ分け（クラスタリング）できるかも試しましたが、
          <strong>できませんでした。</strong>
          どの設定でも大半が「どの群にも属さない」となり、
          全体を群に切ることはできません。立地は連続していて、
          はっきりした型に分かれないというのが実測の結果です。
        </p>
        <p className="note">
          両極にあたる少数（全体の 7.5%）だけは言葉にできます —
          低く平らな土地に置かれた一群と、周囲から突き出た小高い場所に置かれた一群です。
          残りは連続しています。
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
