/**
 * T-061: 詳細ファイルの分割の鍵は、Python と TypeScript で同じ規則である。
 *
 * 画面は `shardOf(id)` でファイル名を決めて取りに行く。Python 側
 * (scripts/build_map_assets.py の shard_of)と規則がずれると、
 * **型もテストも緑のまま、押した古墳の詳細だけが 404 になる**。
 * だから実際に出力されたファイルの中身と突き合わせる(HC-190)。
 */
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { shardOf } from "../../src/lib/shard";

const DETAILS = path.resolve(__dirname, "..", "..", "public", "data", "kofun-details");

describe("T-061 詳細の分割鍵の言語間契約", () => {
  const files = readdirSync(DETAILS).filter((f) => f.endsWith(".json"));

  it("走査対象が空でない", () => {
    expect(files.length).toBeGreaterThan(0);
  });

  it("すべての ID について shardOf が、その ID を実際に含むファイル名を返す", () => {
    let checked = 0;
    const wrong: string[] = [];
    for (const file of files) {
      const members = JSON.parse(readFileSync(path.join(DETAILS, file), "utf-8")) as Record<string, unknown>;
      for (const id of Object.keys(members)) {
        checked++;
        if (`${shardOf(id)}.json` !== file) wrong.push(`${id} → ${shardOf(id)}.json(実際は ${file})`);
      }
    }
    expect(checked).toBeGreaterThan(0);
    expect(wrong, wrong.slice(0, 3).join(" / ")).toEqual([]);
  });

  it("陽性対照: 形の違う ID は例外にする(黙って別のファイルを引かない)", () => {
    expect(() => shardOf("shrine_1234")).toThrow();
    expect(() => shardOf("kofun_a")).toThrow();
  });
});
