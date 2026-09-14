/**
 * T-068: 印の半径の規則(SPEC §3.14)。
 *
 * **実装の後に書いた検査**である(stage 3 の赤確認は経ていない)。
 * 期待値の出所は閉形式: 間隔 d の正方格子では、ある点の最近傍は距離 d にある。
 * 「中心間距離が直径 2r 未満の相手を持つ」は 2r > d のとき全点で成り立ち、2r ≤ d のとき 0 点。
 */
import { describe, expect, it } from "vitest";

import { chooseRadius, overlapFraction } from "../../src/lib/explore";

function grid(spacing: number, n: number): [number, number][] {
  const pts: [number, number][] = [];
  for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) pts.push([i * spacing, j * spacing]);
  return pts;
}

describe("T-068 印の半径の規則", () => {
  it("格子の間隔が直径より狭ければ全点が重なる", () => {
    // 間隔 5 に対して直径 8(半径 4)
    expect(overlapFraction(grid(5, 10), 4)).toBe(1);
  });

  it("格子の間隔が直径以上なら重なりは 0(ちょうど等しいときは『未満』に当たらない)", () => {
    expect(overlapFraction(grid(8, 10), 4)).toBe(0);
    expect(overlapFraction(grid(5, 10), 2)).toBe(0);
  });

  it("孤立した点が混ざると割合はその分だけ下がる(閉形式)", () => {
    const pts = grid(5, 10); // 100 点、全点が重なる
    for (let k = 0; k < 25; k++) pts.push([1000 + k * 100, 1000]); // 25 点の孤立点
    expect(overlapFraction(pts, 4)).toBeCloseTo(100 / 125, 12);
  });

  it("chooseRadius は 4 で上限以下ならそれを採る", () => {
    const r = chooseRadius(grid(10, 10));
    expect(r.radius).toBe(4);
    expect(Object.keys(r.fractions)).toEqual(["4"]);
  });

  it("chooseRadius は上限を超える間は下げ、最初に上限以下になった半径を採る", () => {
    // 間隔 7: 半径 4(直径 8)は全点重なる、半径 3(直径 6)は 0
    const r = chooseRadius(grid(7, 10));
    expect(r.radius).toBe(3);
    expect(r.fractions[4]).toBe(1);
    expect(r.fractions[3]).toBe(0);
  });

  it("どれも上限を超えるなら最小の半径を採る", () => {
    const r = chooseRadius(grid(3, 10));
    expect(r.radius).toBe(2);
    expect(r.fractions[2]).toBe(1);
  });

  it("陽性対照: 上限を 1 にするとどの格子でも最初の候補を採る", () => {
    expect(chooseRadius(grid(3, 10), [4, 3, 2], 1).radius).toBe(4);
  });
});
