const GITHUB_URL = "https://github.com/tetsuro-sakata/kofun-atlas-ai";
const APP_MENU_URL = "https://app-menu-tau.vercel.app/";

/**
 * フリート共通フッタ(koho-lens 準拠)。
 *
 * 規約は 5 項目「MIT License © 2026 坂田哲朗 ・ GitHub ・ 歩き方 ・ 設計図 ・ App Menu」。
 * 「歩き方」「設計図」の解説アーティファクトは公開ループ(L7)で作るので、
 * それまでは項目を出さない —— 存在しない先へのリンクを出さないため。
 */
const GUIDE_URL: string | null = null;
const BLUEPRINT_URL: string | null = null;

export default function Footer() {
  return (
    <footer className="fleet-footer">
      <span>MIT License © 2026 坂田哲朗</span>
      <span aria-hidden="true">・</span>
      <a href={GITHUB_URL} target="_blank" rel="noreferrer">
        GitHub
      </a>
      {GUIDE_URL && (
        <>
          <span aria-hidden="true">・</span>
          <a href={GUIDE_URL} target="_blank" rel="noreferrer">
            古墳アトラスの歩き方
          </a>
        </>
      )}
      {BLUEPRINT_URL && (
        <>
          <span aria-hidden="true">・</span>
          <a href={BLUEPRINT_URL} target="_blank" rel="noreferrer">
            古墳アトラスの設計図
          </a>
        </>
      )}
      <span aria-hidden="true">・</span>
      <a href={APP_MENU_URL} target="_blank" rel="noreferrer">
        App Menu
      </a>
    </footer>
  );
}
