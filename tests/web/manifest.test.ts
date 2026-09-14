/**
 * T-027: 画面が読む `data-manifest.json` の契約。
 *
 * 画面に出す数値は Python 側で作り、TypeScript 側は読むだけである(HC-152)。
 * その境界は型の外にあるので、**欄が消えたことも、意味が入れ替わったことも
 * ビルドでは分からない**。ここで契約として固定する。
 *
 * 期待値の出所: SPEC §3.2 / §7 G-01。件数は定数で書かず、
 * 欄の存在と数どうしの関係(不変量)で書く。
 */
import { describe, expect, it } from "vitest";

import manifest from "../../public/data/data-manifest.json";

const MIN_RECORDS = 2000; // SPEC §7 G-01

describe("data-manifest.json", () => {
  it("画面が読む欄がすべてある", () => {
    for (const key of [
      "geoshape_rows",
      "merged_duplicate_rows",
      "records",
      "with_prefecture",
      "without_muni_cd",
      "with_coordinates",
      "with_mound_type",
      "with_chronology",
      "prefecture_corrected",
    ]) {
      expect(manifest.counts, `counts.${key} が無い`).toHaveProperty(key);
    }
    expect(manifest.sources.length).toBeGreaterThan(0);
    for (const source of manifest.sources) {
      expect(source.credit).toBeTruthy();
      expect(source.license).toBeTruthy();
      expect(source.retrieved_at).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    }
  });

  it("件数どうしが辻褄の合う関係になっている", () => {
    const c = manifest.counts;
    expect(c.records).toBeGreaterThanOrEqual(MIN_RECORDS);
    // 統合した分だけ元の行数より減る。
    expect(c.records + c.merged_duplicate_rows).toBe(c.geoshape_rows);
    // 県が付いた件と付かなかった件で全件になる。
    expect(c.with_prefecture + c.without_muni_cd).toBe(c.records);
    expect(c.with_coordinates).toBe(c.records);
    // 覆した件は、県が付いた件の内数にしかなりえない。
    expect(c.prefecture_corrected).toBeLessThanOrEqual(c.with_prefecture);
  });

  it("都道府県の内訳の合計が、県の付いた件数と一致する", () => {
    const byPref = manifest.prefectures as Record<string, number>;
    const total = Object.values(byPref).reduce((a, b) => a + b, 0);
    expect(total).toBe(manifest.counts.with_prefecture);
  });

  it("公開したことが明示されている", () => {
    // L7(2026-09-15)で公開する。false に戻るのは意図した変更のときだけ。
    expect(manifest.shipped).toBe(true);
  });
});
