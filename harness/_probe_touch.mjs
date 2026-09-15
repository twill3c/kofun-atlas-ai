/**
 * スマホ(タッチ)で主要な操作が届くかの探針。app-menu の「スマホ対応」を名乗る前に測る。
 *
 * 画面幅 320 / 360 px で溢れないことは検品器が測っているが、**指で操作できるかは測っていない**
 * (physics-puzzle-lab は幅だけ見て mobile:true にし、タッチで板を回せなかった)。
 * ここではタッチ有効のモバイル端末を模して、本番に対して次を試す:
 *   1. 地図: 検索欄をタップして名前を入れ、結果をタップすると詳細が開く
 *   2. 地図: 似た立地のボタンをタップすると一覧が 10 件出る
 *   3. 地図: 描かれた点をタップすると詳細が開く
 *   4. 探索: 散布図の点をタップすると名前が出る(ホバーの代わりが効くか)
 *   5. 探索: 県の強調を選ぶと一覧の件数が変わる
 *   6. 各ページが 390 px で横に溢れない
 *
 *   node harness/_probe_touch.mjs [https://kofun-atlas-ai.vercel.app]
 */
import { readFile } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const BASE = (process.argv[2] ?? "https://kofun-atlas-ai.vercel.app").replace(/\/$/, "");
const points = JSON.parse(await readFile(path.join(process.cwd(), "out", "data", "kofun-points.geojson"), "utf-8"));
const results = [];
const record = (name, ok, detail = "") => {
  results.push({ name, ok, detail });
  console.log(`  ${ok ? "OK  " : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
};

const browser = await chromium.launch();
try {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();

  // --- 1〜3 地図 ------------------------------------------------------------
  await page.goto(`${BASE}/map/`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => {
    const m = window.__kofunMap;
    // 層が在るかを先に聞く(無い層を問うと MapLibre が error を出し、画面がそれを表示する)
    return !!m && m.isStyleLoaded() && !!m.getLayer("kofun-points")
      && m.queryRenderedFeatures({ layers: ["kofun-points"] }).length > 0;
  }, null, { timeout: 30000 }).catch(() => {});

  const name = points.features[0].properties.name;
  const input = page.locator('.map-panel input[type="search"]');
  await input.tap().catch(() => {});
  await input.fill(name).catch(() => {});
  const hit = page.locator(".result-list button", { hasText: name }).first();
  await hit.tap({ timeout: 10000 }).catch(() => {});
  const title = (await page.locator("#detail-title").textContent({ timeout: 10000 }).catch(() => null))?.trim();
  record("地図: 検索結果をタップすると詳細が開く", title === name, `探した=${name} 見出し=${title}`);

  const simButton = page.getByRole("button", { name: /似た/ }).first();
  await simButton.tap({ timeout: 10000 }).catch(() => {});
  await page.locator(".similar-list li").first().waitFor({ timeout: 10000 }).catch(() => {});
  const simCount = await page.locator(".similar-list li").count();
  record("地図: 似た立地のボタンをタップすると一覧が出る", simCount === 10, `件数=${simCount}`);

  // 点のタップ: 画面の中に描かれている点を 1 つ選び、その画面座標をタップする
  await page.goto(`${BASE}/map/`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => {
    const m = window.__kofunMap;
    // 層が在るかを先に聞く(無い層を問うと MapLibre が error を出し、画面がそれを表示する)
    return !!m && m.isStyleLoaded() && !!m.getLayer("kofun-points")
      && m.queryRenderedFeatures({ layers: ["kofun-points"] }).length > 0;
  }, null, { timeout: 30000 }).catch(() => {});
  const target = await page.evaluate(() => {
    const m = window.__kofunMap;
    const canvas = m.getCanvas().getBoundingClientRect();
    for (const f of m.queryRenderedFeatures({ layers: ["kofun-points"] })) {
      const p = m.project(f.geometry.coordinates);
      if (p.x > 30 && p.y > 30 && p.x < canvas.width - 30 && p.y < canvas.height - 30) {
        return { x: canvas.left + p.x, y: canvas.top + p.y, name: f.properties.name };
      }
    }
    return null;
  });
  if (target) {
    await page.touchscreen.tap(target.x, target.y);
    const t2 = (await page.locator("#detail-title").textContent({ timeout: 10000 }).catch(() => null))?.trim();
    record("地図: 描かれた点をタップすると詳細が開く", !!t2, `タップした点=${target.name} 見出し=${t2}`);
  } else {
    record("地図: 描かれた点をタップすると詳細が開く", false, "タップできる位置に点が見つからない");
  }

  // --- 4〜5 探索 ------------------------------------------------------------
  await page.goto(`${BASE}/explore/`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelectorAll(".scatter svg circle[data-i]").length > 0, null,
    { timeout: 30000 }).catch(() => {});
  await page.locator(".scatter svg").scrollIntoViewIfNeeded().catch(() => {});
  const dot = await page.evaluate(() => {
    const svg = document.querySelector(".scatter svg");
    const c = svg?.querySelector("circle[data-i]");
    if (!svg || !c) return null;
    const p = new DOMPoint(Number(c.getAttribute("cx")), Number(c.getAttribute("cy"))).matrixTransform(svg.getScreenCTM());
    return { x: p.x, y: p.y };
  });
  if (dot) {
    await page.touchscreen.tap(dot.x, dot.y);
    const tip = await page.locator(".tooltip strong").textContent({ timeout: 3000 }).catch(() => null);
    record("探索: 散布図の点をタップすると名前が出る", !!tip, `名前=${tip}`);
  } else {
    record("探索: 散布図の点をタップすると名前が出る", false, "点が見つからない");
  }
  // 点の GeoJSON の欄名は pref(最初は prefecture と書き、undefined を選ぼうとして落ちた)
  const pref = points.features[0].properties.pref;
  await page.selectOption(".filter-row select >> nth=1", pref).catch(() => {});
  const shown = await page.locator("section [aria-live]").textContent({ timeout: 5000 }).catch(() => "");
  record("探索: 県の強調を選ぶと一覧の件数が出る", /\d/.test(shown ?? ""), `県=${pref} 表示=${shown}`);

  // --- 6 横溢れ -------------------------------------------------------------
  for (const route of ["/", "/map/", "/explore/", "/compare/", "/sources/", "/methodology/"]) {
    await page.goto(`${BASE}${route}`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(500);
    const m = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
    record(`${route} が 390 px(タッチ端末)で横に溢れない`, m.sw <= m.cw + 1, `scrollWidth=${m.sw} clientWidth=${m.cw}`);
  }
} finally {
  await browser.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} OK`);
process.exit(failed.length ? 1 : 0);
