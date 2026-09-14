/**
 * T-062〜T-065: 探索画面の範囲選択と集計の二実装照合(SPEC §3.14 G-30 / G-31)。
 *
 * 照合表 tests/fixtures/explore-reference.json は scripts/build_explore_assets.py が
 * 宣言した規則を素の Python で書き下ろして作る。ここでは画面が使う TypeScript 実装の出力を突き合わせ、
 * 規則を一つだけずらした変異体がそれぞれ落ちることを陽性対照にする。
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { classOf, median, quantileBreaks, selectInRect, type Rect } from "../../src/lib/explore";

const ROOT = path.resolve(__dirname, "..", "..");
const TOLERANCE = 1e-9;
const METRICS = ["elevation_m", "slope_deg", "openness_500m"] as const;

type Explore = {
  ids: string[];
  pref: (string | null)[];
  xy: [number, number][];
  metrics: Record<(typeof METRICS)[number], (number | null)[]>;
};
type Reference = {
  rects: (Rect & { label: string; ids: number[] })[];
  prefecture: Record<string, Record<string, number | null>>;
  breaks: Record<string, number[]>;
  class_counts: Record<string, number[]>;
};

const explore: Explore = JSON.parse(readFileSync(path.join(ROOT, "public", "data", "explore.json"), "utf-8"));
const ref: Reference = JSON.parse(
  readFileSync(path.join(ROOT, "tests", "fixtures", "explore-reference.json"), "utf-8"),
);

const close = (a: number | null, b: number | null) =>
  a === null || b === null ? a === b : Math.abs(a - b) <= TOLERANCE;

/** 照合表と食い違った矩形の数。 */
function rectMismatches(select: (xy: [number, number][], r: Rect) => number[]) {
  return ref.rects.filter((r) => JSON.stringify(select(explore.xy, r)) !== JSON.stringify(r.ids)).length;
}

/** 照合表と食い違った (県, 指標) の数。 */
function medianMismatches(med: (v: (number | null)[]) => number | null) {
  let bad = 0;
  for (const [pref, entry] of Object.entries(ref.prefecture)) {
    const members = explore.pref.flatMap((p, i) => (p === pref ? [i] : []));
    if (members.length !== entry.count) bad++;
    for (const m of METRICS) {
      if (!close(med(members.map((i) => explore.metrics[m][i])), entry[m] as number | null)) bad++;
    }
  }
  return bad;
}

describe("T-062 範囲選択の二実装照合", () => {
  it("照合表の前提: 点 0 個の矩形と全点の矩形があり、辺ちょうどの点が実在する", () => {
    const counts = ref.rects.map((r) => r.ids.length);
    expect(counts).toContain(0);
    expect(counts).toContain(explore.xy.length);
    const onEdge = ref.rects.some((r) =>
      r.ids.some((i) => {
        const [x, y] = explore.xy[i];
        return x === r.x0 || x === r.x1 || y === r.y0 || y === r.y1;
      }),
    );
    // 辺ちょうどの点が無ければ「辺を含むか」の変異体は落ちようがない(HC-070)。
    expect(onEdge).toBe(true);
  });

  it("矩形 6 つすべてで、選ばれる点の番号集合が Python と一致する", () => {
    expect(rectMismatches(selectInRect)).toBe(0);
  });
});

describe("T-063 範囲選択の陽性対照", () => {
  it("辺を含まない実装は落ちる", () => {
    const exclusive = (xy: [number, number][], r: Rect) =>
      xy.flatMap(([x, y], i) => (r.x0 < x && x < r.x1 && r.y0 < y && y < r.y1 ? [i] : []));
    expect(rectMismatches(exclusive)).toBeGreaterThan(0);
  });

  it("x と y を入れ替えた実装は落ちる", () => {
    const swapped = (xy: [number, number][], r: Rect) =>
      selectInRect(xy.map(([x, y]) => [y, x] as [number, number]), r);
    expect(rectMismatches(swapped)).toBeGreaterThan(0);
  });
});

describe("T-064 集計の二実装照合", () => {
  it("都道府県ごとの件数と三指標の中央値が Python と一致する", () => {
    expect(medianMismatches(median)).toBe(0);
  });

  it("分位の境界 4 つと各クラスの件数が Python と一致する", () => {
    for (const m of METRICS) {
      const breaks = quantileBreaks(explore.metrics[m]);
      expect(breaks.length).toBe(4);
      breaks.forEach((b, j) => expect(close(b, ref.breaks[m][j]), `${m} 境界 ${j}`).toBe(true));
      const counts = [0, 0, 0, 0, 0];
      for (const v of explore.metrics[m]) {
        const c = classOf(v, breaks);
        if (c !== null) counts[c]++;
      }
      expect(counts, m).toEqual(ref.class_counts[m]);
    }
  });
});

describe("T-065 集計の陽性対照", () => {
  it("前提: 値の数が偶数個の県が実在する", () => {
    const even = Object.values(ref.prefecture).filter((e) => (e.elevation_m__nonnull as number) % 2 === 0);
    // 偶数個の県が無ければ「下の真ん中を採る」変異体は落ちようがない。
    expect(even.length).toBeGreaterThan(0);
  });

  it("平均で代用する実装は落ちる", () => {
    const mean = (v: (number | null)[]) => {
      const xs = v.filter((x): x is number => x !== null);
      return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
    };
    expect(medianMismatches(mean)).toBeGreaterThan(0);
  });

  it("偶数個で下の真ん中を採る実装は落ちる", () => {
    const lowerMiddle = (v: (number | null)[]) => {
      const xs = v.filter((x): x is number => x !== null).sort((a, b) => a - b);
      return xs.length ? xs[Math.floor((xs.length - 1) / 2)] : null;
    };
    expect(medianMismatches(lowerMiddle)).toBeGreaterThan(0);
  });

  it("境界の添字を切り上げる実装は落ちる", () => {
    let differs = 0;
    for (const m of METRICS) {
      const xs = explore.metrics[m].filter((x): x is number => x !== null).sort((a, b) => a - b);
      const ceilBreaks = [1, 2, 3, 4].map((j) => xs[Math.min(xs.length - 1, Math.ceil((j * xs.length) / 5))]);
      if (ceilBreaks.some((b, j) => !close(b, ref.breaks[m][j]))) differs++;
    }
    expect(differs).toBeGreaterThan(0);
  });
});
