/**
 * T-056 / T-057: 類似検索の二実装照合と陽性対照(SPEC §3.12 G-26)。
 *
 * 照合表 tests/fixtures/similar-top10.json は scripts/build_map_assets.py が
 * 配った埋め込みの内積から**独立に**作る(kofun_atlas.features を使わない)。
 * ここでは TypeScript 実装の出力を、ID・順序・類似度の値の三つで突き合わせる ——
 * 結論(ID)だけでなく経路(類似度)も比べる(HC-065)。
 *
 * 並べる規則は SPEC §3.12 に宣言したとおり:
 * 類似度の降順、同点ならレコードの並び順の昇順、自分自身は除く。
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { topK, type Neighbour } from "../../src/lib/similarity";

const ROOT = path.resolve(__dirname, "..", "..");
const SCORE_TOLERANCE = 1e-9;

/*
 * 時間制限。全 2,805 件 × 全候補の内積を並べるので重い。実測(2026-09-14):
 * 単独実行で 2,122〜3,770ms、Python の全件や撮影と並行させると 5,301〜5,440ms になり、
 * vitest の既定 5,000ms を越えて「Test timed out」で落ちた(食い違いではない —— 制限を 1,000ms に
 * 縮めると重いテストだけが同じ型で落ちることを陽性対照で確かめた)。
 * 固定の時間予算は正しさでなく機械の混み具合を測る(HC-245)。
 * **延ばしても照合は骨抜きにならない**: T-057 の変異体 3 つが照合で落ちることを毎回確かめている。
 */
const HEAVY_TIMEOUT_MS = 60_000;

type Fixture = {
  top_k: number;
  ids: string[];
  neighbours: number[][];
  scores: number[][];
};

const embeddings: { ids: string[]; embeddings: number[][] } = JSON.parse(
  readFileSync(path.join(ROOT, "public", "data", "embeddings.json"), "utf-8"),
);
const fixture: Fixture = JSON.parse(
  readFileSync(path.join(ROOT, "tests", "fixtures", "similar-top10.json"), "utf-8"),
);
const vectors = embeddings.embeddings;

/** 照合表と食い違った行の数と、最初の食い違いを返す。 */
function mismatches(search: (q: number) => Neighbour[]) {
  let bad = 0;
  let first: string | null = null;
  for (let q = 0; q < vectors.length; q++) {
    const got = search(q);
    const wantIds = fixture.neighbours[q];
    const wantScores = fixture.scores[q];
    const same =
      got.length === wantIds.length &&
      got.every(
        (n, i) =>
          n.index === wantIds[i] && Math.abs(n.score - wantScores[i]) <= SCORE_TOLERANCE,
      );
    if (!same) {
      bad++;
      if (first === null) {
        first = `q=${q} got=${JSON.stringify(got.map((n) => n.index))} want=${JSON.stringify(wantIds)}`;
      }
    }
  }
  return { bad, first };
}

function dot(a: number[], b: number[]): number {
  let s = 0;
  for (let i = 0; i < a.length; i++) s += a[i] * b[i];
  return s;
}

describe("T-056 類似検索の二実装照合", { timeout: HEAVY_TIMEOUT_MS }, () => {
  it("照合表と埋め込みが同じ並びを前提にしている", () => {
    expect(fixture.ids).toEqual(embeddings.ids);
    expect(fixture.neighbours.length).toBe(vectors.length);
    expect(fixture.top_k).toBe(10);
  });

  it("全件で上位 10 件の ID・順序・類似度が Python と一致する", () => {
    const { bad, first } = mismatches((q) => topK(vectors, q, fixture.top_k));
    expect(bad, `食い違い ${bad} 件。最初: ${first}`).toBe(0);
  });

  it("自分自身を返さない", () => {
    for (let q = 0; q < vectors.length; q += 97) {
      expect(topK(vectors, q, 10).some((n) => n.index === q)).toBe(false);
    }
  });
});

describe("T-057 陽性対照 — 変異体はそれぞれ照合で落ちる", { timeout: HEAVY_TIMEOUT_MS }, () => {
  /** 共通の土台: 規則だけを差し替えられる参照実装。 */
  function variant(
    q: number,
    k: number,
    opts: { keepSelf?: boolean; ascending?: boolean; tieDesc?: boolean },
  ): Neighbour[] {
    const all: Neighbour[] = [];
    for (let i = 0; i < vectors.length; i++) {
      if (i === q && !opts.keepSelf) continue;
      all.push({ index: i, score: dot(vectors[q], vectors[i]) });
    }
    all.sort((a, b) => {
      if (a.score !== b.score) return opts.ascending ? a.score - b.score : b.score - a.score;
      return opts.tieDesc ? b.index - a.index : a.index - b.index;
    });
    return all.slice(0, k);
  }

  it("対照が撃つ前提: 変異させない土台は照合を通る", () => {
    // 土台そのものが照合に落ちるなら、変異体が落ちても何も言えない。
    expect(mismatches((q) => variant(q, 10, {})).bad).toBe(0);
  });

  it("対照が撃つ前提: 照合表の上位 10 件に同点が実在する", () => {
    let ties = 0;
    for (const row of fixture.scores) {
      for (let i = 1; i < row.length; i++) if (row[i] === row[i - 1]) ties++;
    }
    // 同点が無ければ (c) の変異体は落ちようがない(HC-070)。
    expect(ties).toBeGreaterThan(0);
  });

  it("(a) 自分自身を除かない実装は落ちる", () => {
    expect(mismatches((q) => variant(q, 10, { keepSelf: true })).bad).toBeGreaterThan(0);
  });

  it("(b) 類似度の昇順で並べる実装は落ちる", () => {
    expect(mismatches((q) => variant(q, 10, { ascending: true })).bad).toBeGreaterThan(0);
  });

  it("(c) 同点をレコード順の降順にする実装は落ちる", () => {
    expect(mismatches((q) => variant(q, 10, { tieDesc: true })).bad).toBeGreaterThan(0);
  });
});
