/**
 * 探針: 地図右下の出典表示が読めるか(撮影で見た「文字がほとんど見えない」を実測する — HC-194)。
 *
 * 仮説: ページの暗色テーマ(body の文字色 #f2ece1・リンク色 #c8813a)が MapLibre の
 * 出典欄に継承され、半透明の白地の上で明るい文字になっている。
 *
 * 出典欄の中の各テキストについて、計算済みの文字色と、実際に背後にある背景色を
 * 祖先をたどって合成し、WCAG のコントラスト比を出す。
 *
 *   node harness/_probe_attrib_contrast.mjs
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

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(`${base}/map/`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".maplibregl-ctrl-attrib", { timeout: 30000 });
  // 待つ条件は「何か文字がある」ではなく「両方の出典が出た」。国土地理院の出典は背景地図と一緒に
  // 先に出て、古墳の出典(CODH)は点のデータを読み込んだ後で足される。最初の版はその間に読んでいた。
  await page.waitForFunction(() => {
    const t = document.querySelector(".maplibregl-ctrl-attrib-inner")?.textContent ?? "";
    return t.includes("国土地理院") && t.includes("CODH");
  }, null, { timeout: 30000 });

  const result = await page.evaluate(() => {
    const parse = (c) => {
      const m = c.match(/rgba?\(([^)]+)\)/);
      if (!m) return [0, 0, 0, 0];
      const [r, g, b, a = 1] = m[1].split(",").map((x) => parseFloat(x));
      return [r, g, b, a];
    };
    const lum = ([r, g, b]) => {
      const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
      return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
    };
    const over = (top, under) => {
      const a = top[3];
      return [0, 1, 2].map((i) => top[i] * a + under[i] * (1 - a)).concat(1);
    };
    // 背後の背景の合成を二通りで出して比べる。
    //   旧モデル: 祖先の背景色を html まで全部たどる。**祖先に不透明な body(暗色)があるので、
    //            地図の色(ground)を上書きしてしまう** —— 海と陸で値が毎回同じだったのはこのため。
    //   新モデル: 地図の器(.maplibregl-map)の手前で止める。出典欄の真後ろに描かれているのは
    //            祖先ではなく**兄弟のキャンバス**(地図タイル)なので、ground から合成を始める。
    const effectiveBg = (el, ground, stopAtMap) => {
      const chain = [];
      for (let n = el; n; n = n.parentElement) {
        if (stopAtMap && n.classList?.contains("maplibregl-map")) break;
        chain.push(getComputedStyle(n).backgroundColor);
      }
      let bg = [...ground, 1];
      for (const c of chain.reverse()) bg = over(parse(c), bg);
      return bg;
    };
    const ratio = (a, b) => {
      const [l1, l2] = [lum(a), lum(b)].sort((x, y) => y - x);
      return (l1 + 0.05) / (l2 + 0.05);
    };
    const inner = document.querySelector(".maplibregl-ctrl-attrib-inner");
    const ctrl = document.querySelector(".maplibregl-ctrl-attrib");
    const nodes = [inner, ...inner.querySelectorAll("a")];
    const rows = nodes.map((n) => {
      const color = parse(getComputedStyle(n).color);
      const m = (ground, stop) => +ratio(color, effectiveBg(n, ground, stop)).toFixed(2);
      return {
        tag: n.tagName.toLowerCase(),
        text: (n.tagName === "A" ? n.textContent : [...n.childNodes].filter((c) => c.nodeType === 3).map((c) => c.textContent).join("")).trim().slice(0, 40),
        color: getComputedStyle(n).color,
        oldModel: { sea: m([189, 214, 246], false), land: m([255, 255, 255], false) },
        newModel: { sea: m([189, 214, 246], true), land: m([255, 255, 255], true) },
      };
    });
    return {
      controlBackground: getComputedStyle(ctrl).backgroundColor,
      bodyBackground: getComputedStyle(document.body).backgroundColor,
      rows,
    };
  });
  console.log(JSON.stringify(result, null, 2));
  console.log("WCAG AA の基準: 通常の文字 4.5 以上 / 大きい文字 3.0 以上");
} finally {
  await browser.close();
  server.close();
}
