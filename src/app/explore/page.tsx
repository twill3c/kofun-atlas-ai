import type { Metadata } from "next";

import ExploreView from "@/components/ExploreView";

export const metadata: Metadata = {
  title: "立地の探索 | Kofun Atlas AI",
  description: "古墳の置かれた場所の特徴を二次元に並べた図。近い点どうしは立地が似ている。",
};

export default function ExplorePage() {
  return (
    <div className="wrap wide">
      <h1>立地の探索</h1>
      <p className="lede">
        各古墳の置かれた場所（地形と、まわりにどれだけ古墳があるか）を二次元に並べました。近くにある点どうしは立地が似ています。
      </p>
      <p className="note notice">
        これは<strong>古墳そのものの特徴ではありません。</strong>墳形・墳丘長・築造時期・出土品は、再配布できる公開データでは 1 件も埋まっていないためです。群に切ることも試しましたが、立地は連続していて型に分かれませんでした。
      </p>
      <ExploreView />
    </div>
  );
}
