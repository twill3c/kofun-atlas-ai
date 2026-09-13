import type { Metadata } from "next";

import KofunMap from "@/components/KofunMap";
import manifest from "../../../public/data/data-manifest.json";

export const metadata: Metadata = {
  title: "地図 | Kofun Atlas AI",
  description:
    "公開データから集めた古墳 2,805 件の分布。都道府県で絞り込み、名前で探し、立地の似た古墳を探せる。背景は国土地理院淡色地図。",
};

const nf = new Intl.NumberFormat("ja-JP");

export default function MapPage() {
  const prefectures = Object.keys(manifest.prefectures as Record<string, number>);
  return (
    <div className="wrap wide">
      <h1>古墳の分布</h1>
      <p className="lede">
        {nf.format(manifest.counts.records)} 件の古墳を地図に並べています。点を押すと、その場所の地形と、立地の似た古墳を見られます。
      </p>
      <p className="note notice">
        これは再配布できる公開データを集めたもので、<strong>日本の古墳をすべて網羅するものではありません。</strong>
        点の多い少ないは、その地域の古墳の多さではなく、元データにどれだけ載っているかを表します。
      </p>
      <KofunMap prefectures={prefectures} />
    </div>
  );
}
