/**
 * 探針: 描画された本文に「和文␣和文」の余計な空白が混ざっていないか。
 *
 * JSX の本文を途中で改行すると、改行と字下げが空白一つに畳まれる。英文なら正しい語間になるが、
 * 和文では「地形と、␣立地の似た古墳」のような目に見える空白になる(撮影の目視で発見)。
 *
 * **正当な空白もある**(HC-074: 検査を書いたら先に正常系で誤検出を数える)。たとえば検索結果は
 * 名前と所在地を空白で区切っている(「石舞台古墳 奈良県明日香村」)。ここでは検査にせず、
 * 見つかった箇所をすべて前後の文脈つきで列挙して、人が仕分ける。
 *
 *   node harness/_probe_jsx_spaces.mjs
 */
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const OUT = path.join(process.cwd(), "out");
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

// 和文の文字(ひらがな・カタカナ・漢字)と和文の約物。空白の前後が両方これなら拾う。
const JA = "[\\u3040-\\u30ff\\u3400-\\u9fff\\u3000-\\u303f\\uff08\\uff09\\uff0c\\uff1a]";
const PATTERN = new RegExp(`(.{0,12}${JA}) (${JA}.{0,12})`, "gu");

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const scan = async (label) => {
    const text = await page.evaluate(() => {
      // 本文を**要素ごと**に取る。innerText を丸ごと取ると、ブロック要素の境目が改行でなく
      // 空白に見える場所ができ、偽の検出が出る。
      const out = [];
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
      for (let n = walker.currentNode; n; n = walker.nextNode()) {
        const own = [...n.childNodes].filter((c) => c.nodeType === 3).map((c) => c.textContent).join("");
        if (own.trim()) out.push(own.replace(/\s+/g, " "));
      }
      return out;
    });
    const hits = [];
    for (const chunk of text) {
      for (const m of chunk.matchAll(PATTERN)) hits.push(`…${m[1]}␣${m[2]}…`);
    }
    console.log(`== ${label}: ${hits.length} 箇所`);
    for (const h of hits) console.log(`   ${h}`);
  };

  await page.goto(`${base}/`, { waitUntil: "domcontentloaded" });
  await scan("/");

  await page.goto(`${base}/map/`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.__kofunMap?.isStyleLoaded?.() &&
    window.__kofunMap.queryRenderedFeatures({ layers: ["kofun-points"] }).length > 0, null, { timeout: 30000 });
  await page.fill('.map-panel input[type="search"]', "石舞台古墳");
  await page.locator(".result-list button", { hasText: "石舞台古墳" }).first().click();
  await page.waitForSelector("#detail-title", { timeout: 15000 });
  await page.getByRole("button", { name: "立地の似た古墳を探す" }).click();
  await page.waitForFunction(() => document.querySelectorAll(".similar-list li").length === 10, null, { timeout: 30000 });
  await scan("/map/(詳細と似た立地を開いた状態)");
} finally {
  await browser.close();
  server.close();
}
