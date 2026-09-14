/**
 * L6 で足したページを 320 / 768 / 1280 px で撮る(SPEC G-15)。
 *
 * 検品器(smoke.mjs)は溢れや位置を数えるが、読めるかどうかは数えられない。
 * 撮影は嘘をつく(HC-194)ので、固定フッタは撮影中だけ退ける。
 *
 *   node harness/_shot_pages.mjs
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

const hideFooter = (page) => page.evaluate(() => {
  const f = document.querySelector(".fleet-footer");
  if (f) f.style.visibility = "hidden";
});

const browser = await chromium.launch();
try {
  for (const [w, h] of [[320, 700], [768, 1024], [1280, 900]]) {
    const page = await browser.newPage({ viewport: { width: w, height: h } });

    await page.goto(`${base}/explore/`, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => document.querySelectorAll(".scatter svg circle[data-i]").length > 0, null, { timeout: 30000 });
    await hideFooter(page);
    await page.locator(".explore-figures").scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(SHOTS, `explore-${w}-figures.png`) });
    await page.selectOption(".filter-row select >> nth=1", "奈良県");
    await page.waitForSelector(".data-table", { timeout: 10000 });
    await page.locator(".explore-figures").scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(SHOTS, `explore-${w}-emphasis.png`) });
    await page.locator("#selection-title").scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(SHOTS, `explore-${w}-table.png`) });

    for (const route of ["compare", "sources", "methodology"]) {
      await page.goto(`${base}/${route}/`, { waitUntil: "domcontentloaded" });
      await hideFooter(page);
      await page.screenshot({ path: path.join(SHOTS, `${route}-${w}.png`) });
    }
    console.log(`撮影 ${w}px`);
    await page.close();
  }
} finally {
  await browser.close();
  server.close();
}
