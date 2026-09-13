/**
 * 探針: 「似た立地が強調レイヤーに入る 件数=0」は実装の欠陥か、検品器の読み違いか。
 *
 * 仮説: querySourceFeatures は**視野内に読み込まれたタイルの分しか返さない**。
 * 検索結果を押すと対象へ zoom 10 で飛び、似た立地の古墳は全国に散るので視野の外にある。
 *
 * 三つを測る:
 *   (1) querySourceFeatures("similar") の件数       — 検品器が数えていたもの
 *   (2) 似た立地 10 件のうち、今の視野に入っている件数 — 仮説の直接の証拠
 *   (3) 10 件を包む範囲へ寄せた後の querySourceFeatures と描画数 — データは入っているか
 *
 *   node harness/_probe_similar_viewport.mjs
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
const points = JSON.parse(await readFile(path.join(OUT, "data", "kofun-points.geojson"), "utf-8"));
const nameCount = {};
for (const f of points.features) nameCount[f.properties.name] = (nameCount[f.properties.name] ?? 0) + 1;
const target = points.features.find((f) => nameCount[f.properties.name] === 1 && f.properties.name.length >= 4).properties;

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(`${base}/map/`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.__kofunMap?.isStyleLoaded?.() &&
    window.__kofunMap.queryRenderedFeatures({ layers: ["kofun-points"] }).length > 0, null, { timeout: 30000 });
  await page.fill('.map-panel input[type="search"]', target.name);
  await page.locator(".result-list button", { hasText: target.name }).first().click();
  await page.waitForFunction((n) => document.querySelector("#detail-title")?.textContent === n, target.name, { timeout: 15000 });
  await page.getByRole("button", { name: "立地の似た古墳を探す" }).click();
  await page.waitForFunction(() => document.querySelectorAll(".similar-list li").length === 10, null, { timeout: 30000 });
  await page.evaluate(() => new Promise((r) => { const m = window.__kofunMap; m.once("idle", r); m.triggerRepaint(); }));

  const measured = await page.evaluate(async () => {
    const m = window.__kofunMap;
    const idle = () => new Promise((r) => { m.once("idle", r); m.triggerRepaint(); });
    const data = await m.getSource("similar").getData();
    const coords = data.features.map((f) => f.geometry.coordinates);
    const b = m.getBounds();
    const inView = coords.filter(([x, y]) => x >= b.getWest() && x <= b.getEast() && y >= b.getSouth() && y <= b.getNorth()).length;
    const before = {
      zoom: +m.getZoom().toFixed(2),
      querySource: m.querySourceFeatures("similar").length,
      rendered: m.queryRenderedFeatures({ layers: ["similar-points"] }).length,
      dataFeatures: data.features.length,
      inView,
    };
    const xs = coords.map((c) => c[0]);
    const ys = coords.map((c) => c[1]);
    m.fitBounds([[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]], { padding: 40, animate: false });
    await idle();
    const after = {
      zoom: +m.getZoom().toFixed(2),
      querySource: m.querySourceFeatures("similar").length,
      rendered: new Set(m.queryRenderedFeatures({ layers: ["similar-points"] }).map((f) => f.properties.id)).size,
    };
    return { before, after };
  });
  console.log(`対象: ${target.name}`);
  console.log(JSON.stringify(measured, null, 2));
} finally {
  await browser.close();
  server.close();
}
