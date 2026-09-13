/**
 * T-060: フリート共通フッタの宛先。
 *
 * 期待値の出所は**外部権威**としてのフリートの正本
 * `koho-lens/src/render.py` 137〜141 行(2026-09-14 参照)。
 *   MIT License → https://github.com/twill3c/koho-lens/blob/main/LICENSE
 *   GitHub      → https://github.com/twill3c/koho-lens
 *   App Menu    → https://app-menu-amber.vercel.app
 *
 * L0 で書いた宛先(github.com/tetsuro-sakata/… と app-menu-tau.vercel.app)は
 * 実在しない URL だった。検品器が無かったので L0〜L4 の間ずっと緑のままだった。
 * 画面に描かれた href は実ブラウザ検品(harness/smoke.mjs)でも確かめる。
 */
import { describe, expect, it } from "vitest";

import { FLEET_LINKS } from "../../src/lib/fleet";

describe("T-060 フリート共通フッタの宛先", () => {
  it("GitHub はこのリポジトリを指す", () => {
    expect(FLEET_LINKS.github).toBe("https://github.com/twill3c/kofun-atlas-ai");
  });

  it("MIT License はリポジトリの LICENSE を指す", () => {
    expect(FLEET_LINKS.license).toBe(
      "https://github.com/twill3c/kofun-atlas-ai/blob/main/LICENSE",
    );
  });

  it("App Menu は本番を指す", () => {
    expect(FLEET_LINKS.appMenu).toBe("https://app-menu-amber.vercel.app");
  });

  it("陽性対照: L0 の捏造した宛先はどれも含まない", () => {
    const all = Object.values(FLEET_LINKS).join(" ");
    expect(all).not.toMatch(/tetsuro-sakata/);
    expect(all).not.toMatch(/app-menu-tau/);
  });
});
