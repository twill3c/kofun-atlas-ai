/**
 * フリート共通フッタの宛先。
 *
 * 正本は koho-lens/src/render.py 137〜141 行(2026-09-14 参照)。
 * L0 で書いた宛先は実在しない URL だった —— 手で思い出して書かず、正本から写すこと。
 */
const REPO = "https://github.com/twill3c/kofun-atlas-ai";

export const FLEET_LINKS = {
  license: `${REPO}/blob/main/LICENSE`,
  github: REPO,
  appMenu: "https://app-menu-amber.vercel.app",
} as const;
