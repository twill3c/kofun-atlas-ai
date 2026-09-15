/**
 * T-076: 散布図のタップの規則(SPEC §3.14「タップ」)。
 *
 * タッチ端末にはホバーが無い。本番に当てた探針(harness/_probe_touch.mjs)で、点をタップしても名前が出なかった。
 * 期待値の出所は閉形式: 座標を手で置いた点の、距離の二乗の大小と境界(14 ちょうどは含まない)。
 */
import { describe, expect, it } from "vitest";

import { NEAREST_MAX, TAP_MAX_MOVE, isTap, nearestIndex } from "../../src/lib/explore";

describe("T-076 散布図のタップ", () => {
  it("規則の定数が SPEC と同じ(最寄りは 14 以内・タップは移動 2 未満)", () => {
    expect(NEAREST_MAX).toBe(14);
    expect(TAP_MAX_MOVE).toBe(2);
  });

  it("最寄り点は距離の二乗が最小のもの", () => {
    const pts: [number, number][] = [[100, 100], [105, 100], [120, 100]];
    expect(nearestIndex(pts, 104, 100)).toBe(1);
    expect(nearestIndex(pts, 101, 100)).toBe(0);
  });

  it("同じ距離なら番号の小さい方", () => {
    const pts: [number, number][] = [[110, 100], [90, 100]];
    expect(nearestIndex(pts, 100, 100)).toBe(0);
    expect(nearestIndex([[90, 100], [110, 100]], 100, 100)).toBe(0);
  });

  it("14 ちょうどは含まず、14 未満は含む", () => {
    expect(nearestIndex([[114, 100]], 100, 100)).toBeNull();
    expect(nearestIndex([[113.99, 100]], 100, 100)).toBe(0);
    // 斜め: 距離 √(10²+10²)=14.14 は外
    expect(nearestIndex([[110, 110]], 100, 100)).toBeNull();
  });

  it("点が無ければ null", () => {
    expect(nearestIndex([], 0, 0)).toBeNull();
  });

  it("移動が x・y とも 2 未満ならタップ、どちらかが 2 以上なら範囲選択", () => {
    expect(isTap({ ux0: 10, uy0: 10, ux1: 11.9, uy1: 8.1 })).toBe(true);
    expect(isTap({ ux0: 10, uy0: 10, ux1: 12, uy1: 10 })).toBe(false);
    expect(isTap({ ux0: 10, uy0: 10, ux1: 10, uy1: 7.9 })).toBe(false);
  });

  it("陽性対照: 上限を広げた最寄り探索は 14 の外の点を拾う(境界の検査が効いている)", () => {
    expect(nearestIndex([[114, 100]], 100, 100, 15)).toBe(0);
  });
});
