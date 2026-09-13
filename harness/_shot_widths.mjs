/**
 * 複数の画面幅で /map/ を実際に見るための撮影(HC-078)。
 *
 * 検品器(smoke.mjs)は横溢れと縦の伸びを**数える**が、狭い幅で読めるかは数えられない。
 * ここでは幅ごとに、古墳を 1 件選んで似た立地まで出した状態を撮る。
 * 撮影は嘘をつく(HC-194)ので、固定フッタは撮影中だけ退け、地図は再描画を待ってから撮る。
 *
 *   node harness/_shot_widths.mjs
 */
import { createServer } from "node:http";
import { mkdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const OUT = path.join(process.cwd(), "out");
const SHOTS = path.join(process.cwd(), "artifacts", "screenshots");
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".geojson": "application/geo+json" };

const server = createServer(async (req, res) => {
  try {
    const p = decodeURIComponent(new URL(req.url, "http://x").pathname);
    let file = path.join(OUT, p);
    const s = await stat(file).catch(() => null);
    if (!s || s.isDirectory()) file = path.join(file, "index.html");
    res.writeHead(200, { "content-type": MIME[path.extname(file)] ?? "application/octet-stream" });
    res.end(await readFile(file));
  } catch {
    res.writeHead(404);
    res.end();
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;
await mkdir(SHOTS, { recursive: true });

const browser = await chromium.launch();
try {
  // SPEC G-15 の三幅(320 / 768 / 1280)。最初は 360 で撮っていて、指定の最小幅を見ていなかった。
  for (const [w, h] of [[320, 700], [768, 1024], [1280, 900]]) {
    const page = await browser.newPage({ viewport: { width: w, height: h } });
    await page.goto(`${base}/map/`, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => window.__kofunMap?.isStyleLoaded?.() &&
      window.__kofunMap.queryRenderedFeatures({ layers: ["kofun-points"] }).length > 0, null, { timeout: 30000 });
    // 名前は実データで一意に実在すると確かめたものを使う(2026-09-14: 石舞台古墳 1 件)。
    // 最初は「箸墓」で書いたが、出荷データに箸墓古墳は 1 件も無かった(HC-068)。
    await page.fill('.map-panel input[type="search"]', "石舞台古墳");
    const hit = page.locator(".result-list button", { hasText: "石舞台古墳" }).first();
    if ((await hit.count()) === 0) throw new Error("撮影の前提が崩れた: 石舞台古墳が検索結果に無い");
    await hit.scrollIntoViewIfNeeded();
    await hit.click();
    await page.waitForSelector("#detail-title", { timeout: 15000 });
    const btn = page.getByRole("button", { name: "立地の似た古墳を探す" });
    await btn.scrollIntoViewIfNeeded();
    await btn.click();
    await page.waitForFunction(() => document.querySelectorAll(".similar-list li").length === 10, null, { timeout: 30000 });
    await page.waitForFunction(() => !window.__kofunMap.isMoving(), null, { timeout: 15000 });
    await page.evaluate(async () => {
      const m = window.__kofunMap;
      m.resize();
      await new Promise((r) => { m.once("idle", r); m.triggerRepaint(); });
      const f = document.querySelector(".fleet-footer");
      if (f) f.style.visibility = "hidden";
    });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(SHOTS, `map-${w}-top.png`) });
    await page.locator(".detail").scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(SHOTS, `map-${w}-detail.png`) });
    console.log(`撮影 ${w}px → map-${w}-top.png / map-${w}-detail.png`);
    await page.close();
  }
} finally {
  await browser.close();
  server.close();
}
