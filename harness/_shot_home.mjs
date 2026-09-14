/**
 * L7 で書き直したトップページを 320 / 1280 px で撮る(散文と入口を目で読むため)。
 * 固定フッタは撮影中だけ退ける(HC-194)。
 *
 *   node harness/_shot_home.mjs
 */
import { createServer } from "node:http";
import { mkdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const OUT = path.join(process.cwd(), "out");
const SHOTS = path.join(process.cwd(), "artifacts", "screenshots");
const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json" };

const server = createServer(async (req, res) => {
  try {
    let file = path.join(OUT, decodeURIComponent(new URL(req.url, "http://x").pathname));
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
  for (const [w, h] of [[320, 900], [1280, 900]]) {
    const page = await browser.newPage({ viewport: { width: w, height: h } });
    await page.goto(`${base}/`, { waitUntil: "domcontentloaded" });
    await page.evaluate(() => {
      const f = document.querySelector(".fleet-footer");
      if (f) f.style.visibility = "hidden";
    });
    await page.screenshot({ path: path.join(SHOTS, `home-${w}.png`) });
    await page.close();
    console.log(`撮影 home-${w}.png`);
  }
} finally {
  await browser.close();
  server.close();
}
