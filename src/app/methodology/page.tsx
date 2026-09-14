import type { Metadata } from "next";

import manifest from "../../../public/data/data-manifest.json";
import encoder from "../../../data/derived/encoder-metrics.json";
import projection from "../../../data/derived/projection-metrics.json";

export const metadata: Metadata = {
  title: "作り方 | Kofun Atlas AI",
  description: "古墳データの集め方、地形の計算、立地の埋め込み、確かめ方と、していないこと。",
};

const nf = new Intl.NumberFormat("ja-JP");

/*
 * 画面に出す数は、ビルド時に生成物(data-manifest / encoder-metrics / projection-metrics)から読む。
 * 文章に数を手で書くと、実装のテストでは守られない(HC-152)。
 */
export default function MethodologyPage() {
  const { counts } = manifest;
  return (
    <div className="wrap">
      <h1>作り方</h1>
      <p className="lede">データをどう集め、何を計算し、どう確かめたか。そして、していないこと。</p>

      <div className="card">
        <h2>1. 古墳を集める</h2>
        <p>
          『日本歴史地名大系』施設・地点項目データセットのうち、分類が「古墳」の {nf.format(counts.geoshape_rows)}{" "}
          行を取り込み、同じ古墳の重複 {counts.merged_duplicate_rows} 行を統合して {nf.format(counts.records)}{" "}
          件にしました。名前に「古墳」を含むかどうかでは選んでいません（名前に「古墳」を含まない古墳があるためです）。
        </p>
      </div>

      <div className="card">
        <h2>2. 都道府県を決める</h2>
        <p>
          元データの県名と県コードは行ごとに食い違っていたので、どちらも使わず、座標から国土地理院の逆ジオコーダで決めました。元データの県コードを覆した件数は {nf.format(counts.prefecture_corrected)} 件です。
        </p>
      </div>

      <div className="card">
        <h2>3. 地形を計算する</h2>
        <p>
          国土地理院の標高タイルから、各古墳の周囲 1,000 m を見て標高・傾斜・起伏などを計算しました。5 m と 10 m の標高データは画素ごとに重ねています（5 m のタイルは、在っても中身の多くが空のことがあるためです）。水面には標高がないので 0 で埋めず、空のままにしています。
        </p>
        <p className="note">計算の正しさは、傾きの分かっている平面に当てて式どおりの値が出ることで確かめています。</p>
      </div>

      <div className="card">
        <h2>4. 立地の埋め込み（AI）</h2>
        <p>
          地形と「まわりにどれだけ古墳があるか」を、ノイズ除去オートエンコーダで {encoder.latent_dim} 次元のベクトルにしました。入力は {encoder.n_features} 個です。都道府県と緯度経度は入れていません（「同じ地域だから似ている」を学ばせないためです）。
        </p>
        <p>
          測る前に決めた基準で、この埋め込みが素朴な方法の言い換えではないことを確かめました。似た古墳の上位 20 件が、単純な計算の上位 20 件と重なる割合は {encoder.top20_jaccard_vs_baseline.toFixed(3)}（0.90 以上なら「学習した」とは言わない基準）、同じ次元の主成分分析より再構成の誤差が小さい（{encoder.ae_reconstruction_mse.toFixed(4)} ／ {encoder.pca_reconstruction_mse.toFixed(4)}）。
        </p>
        <p className="note">
          言えるのはここまでです。似ていると出た古墳が考古学的に似ているかは、照らし合わせる正解が無いので確かめていません。
        </p>
      </div>

      <div className="card">
        <h2>5. 二次元に並べる・群に切る</h2>
        <p>
          埋め込みを t-SNE で二次元に並べました。近所の並びがどれだけ保たれているか（trustworthiness）は {projection.trustworthiness.toFixed(4)} です。点を無作為に並べ替えると {projection.trustworthiness_shuffled.toFixed(4)} まで下がるので、この指標は並びを見分けています。
        </p>
        <p>
          群に切ることも試しましたが、測る前に決めた基準（どの群にも属さない点が半分未満）をどの設定でも満たさず、機能ごと落としました。
        </p>
      </div>

      <div className="card">
        <h2>していないこと</h2>
        <ul>
          <li>築造時期の推定。教師にできる時期のデータが 1 件も無いためです。</li>
          <li>墳形の分類。同じく墳形のデータが 1 件も無いためです。</li>
          <li>未発見の古墳の場所の推定。</li>
          <li>画像の転載。</li>
        </ul>
      </div>
    </div>
  );
}
