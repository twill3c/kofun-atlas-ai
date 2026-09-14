/**
 * 実ブラウザ検品 — 出荷される `out/` を静的配信して実際に開く(T-059)。
 *
 * 「テストが緑」と「画面が動く」は別である(HC-041)。ここで測るのは
 * 在存ではなく**幾何と到達**(HC-138):
 *   - 地図に点が描かれるまでの時間(固定待ちを置かず、出るまで待って締切で判定 — HC-245)
 *   - 全件を視野に入れたとき、描かれた点の数がデータの件数と一致するか(G-28)
 *   - 点を押すと詳細が開くか、似た立地の一覧が Python の照合表と同じ 1 位を出すか
 *   - 複数の画面幅で横に溢れないか(HC-078)
 *
 * **この検品器は失敗を終了コードで知らせる。** `| tail` の後の $? は tail のもの(HC-080)。
 *   node harness/smoke.mjs          検品する(0 = 合格 / 1 = 不合格 / 2 = 前提不足 / 3 = 検品器が落ちた)
 *   node harness/smoke.mjs --shot   地図の撮影も行う
 */
import { createServer } from "node:http";
import { mkdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const ROOT = process.cwd();
const OUT = path.join(ROOT, "out");
const SHOTS = path.join(ROOT, "artifacts", "screenshots");
const WANT_SHOT = process.argv.includes("--shot");
const RENDER_DEADLINE_MS = Number(process.env.SMOKE_RENDER_DEADLINE_MS ?? 20000);
const EMPTY_CONTROL_WAIT_MS = Number(process.env.SMOKE_EMPTY_CONTROL_MS ?? 8000);

// フリート共通フッタの正本: koho-lens/src/render.py 137〜141 行(2026-09-14 参照)
const CANON = {
  github: "https://github.com/twill3c/kofun-atlas-ai",
  license: "https://github.com/twill3c/kofun-atlas-ai/blob/main/LICENSE",
  appMenu: "https://app-menu-amber.vercel.app",
};

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".geojson": "application/geo+json; charset=utf-8",
  ".onnx": "application/octet-stream",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".txt": "text/plain; charset=utf-8",
  ".md": "text/markdown; charset=utf-8",
};

const failures = [];
function check(name, ok, detail = "") {
  console.log(`  ${ok ? "OK  " : "FAIL"} ${name}${ok || !detail ? "" : ` ${detail}`}`);
  if (!ok) failures.push(`${name} ${detail}`.trim());
}

/**
 * 描画された本文から「和文␣和文」の余計な空白を拾う。
 * JSX の本文を行の途中で改行すると、改行と字下げが空白一つに畳まれる(撮影で見つけた欠陥の常設化)。
 * `innerText` を使う —— スクリプト内の文字列を含まず、ブロックの境目は空白でなく改行になる
 * (最初の探針は要素ごとの文字を集めて <script> の RSC ペイロードまで数え、重複を出した)。
 */
/**
 * 見つけた空白の報告。**件数を必ず先頭に出す** —— 例を 3 件に切っていたとき、見えた 3 件だけを直して
 * 残りの 2 件を次の実行まで持ち越した(loop_006)。例は切ってよいが、切ったことが読めるようにする。
 */
function spacesDetail(spaces) {
  if (spaces.length === 0) return "";
  const shown = spaces.slice(0, 5).join(" ");
  return spaces.length > 5 ? `${spaces.length} 件(先頭 5 件): ${shown}` : `${spaces.length} 件: ${shown}`;
}

async function strayJapaneseSpaces(page) {
  return page.evaluate(() => {
    const JA = "[\\u3040-\\u30ff\\u3400-\\u9fff\\u3000-\\u303f\\uff08\\uff09\\uff0c\\uff1a]";
    const re = new RegExp(`(.{0,10}${JA}) (${JA}.{0,10})`, "gu");
    return [...document.body.innerText.matchAll(re)].map((m) => `…${m[1]}␣${m[2]}…`);
  });
}

function serve() {
  const server = createServer(async (req, res) => {
    try {
      const p = decodeURIComponent(new URL(req.url, "http://x").pathname);
      let file = path.join(OUT, p);
      const s = await stat(file).catch(() => null);
      if (!s || s.isDirectory()) file = path.join(file, "index.html");
      const body = await readFile(file);
      res.writeHead(200, { "content-type": MIME[path.extname(file)] ?? "application/octet-stream" });
      res.end(body);
    } catch {
      res.writeHead(404, { "content-type": "text/plain" });
      res.end("not found");
    }
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

/** 地図の点が「出るまで」待つ。締切を過ぎたらその時点の数を返す(HC-245)。 */
async function waitForRenderedPoints(page, deadlineMs) {
  const started = Date.now();
  try {
    await page.waitForFunction(
      () => {
        const m = window.__kofunMap;
        return !!m && m.isStyleLoaded() && m.queryRenderedFeatures({ layers: ["kofun-points"] }).length > 0;
      },
      null,
      { timeout: deadlineMs, polling: 100 },
    );
  } catch {
    /* 締切。数はこの後で読む */
  }
  const count = await page.evaluate(() => {
    const m = window.__kofunMap;
    if (!m || !m.getLayer("kofun-points")) return 0;
    return m.queryRenderedFeatures({ layers: ["kofun-points"] }).length;
  });
  return { count, elapsedMs: Date.now() - started };
}

/** 状態を変えたら、再描画が終わるのを待ってから読む(同期的に読むと変更前の値が返る)。 */
async function idle(page) {
  await page.evaluate(
    () =>
      new Promise((resolve) => {
        const m = window.__kofunMap;
        if (m.loaded() && !m.isMoving()) {
          m.once("idle", resolve);
          m.triggerRepaint();
        } else {
          m.once("idle", resolve);
        }
      }),
  );
}

async function main() {
  if (!(await stat(OUT).catch(() => null))) {
    console.error("out/ が無い。先に `pnpm build` を実行すること。");
    process.exit(2);
  }
  const points = JSON.parse(await readFile(path.join(OUT, "data", "kofun-points.geojson"), "utf-8"));
  const fixture = JSON.parse(await readFile(path.join(ROOT, "tests", "fixtures", "similar-top10.json"), "utf-8"));
  const total = points.features.length;
  const ids = points.features.map((f) => f.properties.id);
  if (JSON.stringify(ids) !== JSON.stringify(fixture.ids)) {
    console.error("点の並びと照合表の並びが違う。build_map_assets.py を走らせ直すこと。");
    process.exit(2);
  }

  const server = await serve();
  const base = `http://127.0.0.1:${server.address().port}`;
  const origin = new URL(base).origin;
  const browser = await chromium.launch();
  const consoleErrors = [];
  const badSameOrigin = [];

  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
    page.on("pageerror", (e) => consoleErrors.push(String(e)));
    page.on("response", (r) => {
      if (r.status() >= 400 && new URL(r.url()).origin === origin) {
        badSameOrigin.push({ status: r.status(), url: r.url() });
      }
    });

    // --- 地図ページ ---------------------------------------------------------
    console.log("地図ページ");
    const resp = await page.goto(`${base}/map/`, { waitUntil: "domcontentloaded" });
    check("HTTP 200 で開く", resp?.status() === 200, `status=${resp?.status()}`);
    const bodyText = await page.locator("body").innerText();
    check("古墳の出典が本文にある(JS に依存しない)", bodyText.includes("日本歴史地名大系"));
    check("背景地図の出典 国土地理院が本文にある", bodyText.includes("国土地理院"));
    check("網羅しないことが本文にある", bodyText.includes("網羅するものではありません"));

    // G-27: 出るまで待って締切で判定する
    const render = await waitForRenderedPoints(page, RENDER_DEADLINE_MS);
    check(
      `G-27 点が締切 ${RENDER_DEADLINE_MS}ms 以内に描かれる`,
      render.count > 0,
      `描画=${render.count} 経過=${render.elapsedMs}ms`,
    );
    console.log(`       (初めて描かれるまで ${render.elapsedMs}ms)`);

    // G-28: 全件を視野に入れてから数える。queryRenderedFeatures は視野の中身しか返さない。
    const xs = points.features.map((f) => f.geometry.coordinates[0]);
    const ys = points.features.map((f) => f.geometry.coordinates[1]);
    const bounds = [
      [Math.min(...xs), Math.min(...ys)],
      [Math.max(...xs), Math.max(...ys)],
    ];
    await page.evaluate((b) => window.__kofunMap.fitBounds(b, { padding: 30, animate: false }), bounds);
    await idle(page);
    const geo = await page.evaluate(() => {
      const m = window.__kofunMap;
      const feats = m.queryRenderedFeatures({ layers: ["kofun-points"] });
      const unique = new Set(feats.map((f) => f.properties.id));
      const b = m.getBounds();
      const outside = feats.filter((f) => {
        const [x, y] = f.geometry.coordinates;
        return x < b.getWest() || x > b.getEast() || y < b.getSouth() || y > b.getNorth();
      }).length;
      return { rendered: feats.length, unique: unique.size, outside };
    });
    check("G-28 全件を視野に入れると描画された点の数がデータ件数と一致する", geo.unique === total,
      `描画(一意)=${geo.unique} データ=${total} 生の返り値=${geo.rendered}`);
    check("描かれた点がすべて表示範囲の中にある", geo.outside === 0, `範囲外=${geo.outside}`);

    // キャンバスが器を埋めているか(空白の帯は在存検査にも横溢れ検査にも捕まらない)
    const fit = await page.evaluate(() => {
      const c = document.querySelector(".maplibregl-canvas");
      const box = c.closest(".maplibregl-map");
      const a = c.getBoundingClientRect();
      const b = box.getBoundingClientRect();
      return { cw: Math.round(a.width), ch: Math.round(a.height), bw: Math.round(b.width), bh: Math.round(b.height),
        dx: Math.round(a.left - b.left), dy: Math.round(a.top - b.top) };
    });
    check("キャンバスが器を埋めている", Math.abs(fit.cw - fit.bw) <= 2 && Math.abs(fit.ch - fit.bh) <= 2 &&
      Math.abs(fit.dx) <= 2 && Math.abs(fit.dy) <= 2, JSON.stringify(fit));

    // --- 地図上の出典が読めるか(撮影で見つけた欠陥の常設化) ---------------------
    // ページの暗色テーマが出典欄に漏れ、地の文がコントラスト 3.03 まで落ちていた(2026-09-14)。
    // 両方の出典が出るまで待ってから、全文字の WCAG コントラストを計算済みスタイルで測る。
    await page.waitForFunction(() => {
      const t = document.querySelector(".maplibregl-ctrl-attrib-inner")?.textContent ?? "";
      return t.includes("国土地理院") && t.includes("CODH");
    }, null, { timeout: RENDER_DEADLINE_MS }).catch(() => {});
    const attribMeasure = async () => page.evaluate(() => {
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
      const over = (top, under) => [0, 1, 2].map((i) => top[i] * top[3] + under[i] * (1 - top[3])).concat(1);
      const inner = document.querySelector(".maplibregl-ctrl-attrib-inner");
      if (!inner) return { text: "", worst: 0 };
      // 背後は地図タイル。国土地理院淡色地図の海(#bdd6f6)と陸(#ffffff)の両方で測り、悪いほうを取る。
      // **合成は地図の器(.maplibregl-map)の手前で止める。** 出典欄の真後ろに描かれているのは
      // 祖先ではなく兄弟のキャンバスである。祖先を html までたどると不透明な暗色の body が
      // 地図の色を上書きし、海と陸で値が同一になる(最初の版はそれで 2.32 と誤測した。
      // 探針 harness/_probe_attrib_contrast.mjs で旧モデルと新モデルを並べて確かめた)。
      const worstFor = (el) => {
        const color = parse(getComputedStyle(el).color);
        const chain = [];
        for (let n = el; n; n = n.parentElement) {
          if (n.classList?.contains("maplibregl-map")) break;
          chain.push(getComputedStyle(n).backgroundColor);
        }
        return Math.min(...[[189, 214, 246], [255, 255, 255]].map((ground) => {
          let bg = [...ground, 1];
          for (const c of [...chain].reverse()) bg = over(parse(c), bg);
          const [l1, l2] = [lum(color), lum(bg)].sort((x, y) => y - x);
          return (l1 + 0.05) / (l2 + 0.05);
        }));
      };
      const nodes = [inner, ...inner.querySelectorAll("a")];
      return { text: inner.textContent, worst: Math.min(...nodes.map(worstFor)) };
    });
    const attrib = await attribMeasure();
    check("地図上の出典に国土地理院と日本歴史地名大系の両方がある",
      attrib.text.includes("国土地理院") && attrib.text.includes("日本歴史地名大系"), attrib.text.slice(0, 80));
    check("地図上の出典の文字がすべてコントラスト 4.5 以上(WCAG AA)", attrib.worst >= 4.5,
      `最小=${attrib.worst.toFixed(2)}`);
    // 陽性対照: 暗色テーマの本文色を出典欄へ注入すると、この検査は落ちる
    await page.addStyleTag({ content: ".maplibregl-ctrl-attrib, .maplibregl-ctrl-attrib-inner { color: #f2ece1 !important; }", })
      .then(async (handle) => {
        const leaked = await attribMeasure();
        check("陽性対照: 本文色を出典欄に漏らすとコントラスト検査が落ちる", leaked.worst < 4.5,
          `注入後の最小=${leaked.worst.toFixed(2)}`);
        // 合格時も値を出す。修正前の欠陥(本文色の継承)を**正しい測り方で**測った値として記録に使う。
        console.log(`       (出典欄の最小コントラスト: 修正後 ${attrib.worst.toFixed(2)} / 本文色を漏らすと ${leaked.worst.toFixed(2)})`);
        await handle.evaluate((el) => el.remove());
      });

    // 陽性対照 G-28: 層を隠すと検品器が 0 を検出する
    const hidden = await page.evaluate(async () => {
      const m = window.__kofunMap;
      const wait = () => new Promise((r) => { m.once("idle", r); m.triggerRepaint(); });
      const before = m.queryRenderedFeatures({ layers: ["kofun-points"] }).length;
      m.setLayoutProperty("kofun-points", "visibility", "none");
      await wait();
      const after = m.queryRenderedFeatures({ layers: ["kofun-points"] }).length;
      m.setLayoutProperty("kofun-points", "visibility", "visible");
      await wait();
      const restored = m.queryRenderedFeatures({ layers: ["kofun-points"] }).length;
      return { before, after, restored };
    });
    check("陽性対照: 点の層を隠すと検品器が 0 を検出する",
      hidden.before > 0 && hidden.after === 0 && hidden.restored > 0, JSON.stringify(hidden));

    // --- 都道府県の絞り込み(到達の証拠: 描画数がその県の件数になる) ---------
    console.log("都道府県の絞り込み");
    const prefCounts = {};
    for (const f of points.features) prefCounts[f.properties.pref] = (prefCounts[f.properties.pref] ?? 0) + 1;
    const [prefName, prefN] = Object.entries(prefCounts).sort((a, b) => b[1] - a[1])[0];
    await page.selectOption(".map-panel select", prefName);
    await idle(page);
    // evaluate の戻り値は直列化される。Set や Map は境界で `{}` に化けるので、
    // **配列と数だけを返す**(HC-190: 境界をまたぐ値の契約)。
    const filtered = await page.evaluate(() => {
      const feats = window.__kofunMap.queryRenderedFeatures({ layers: ["kofun-points"] });
      return {
        prefs: [...new Set(feats.map((f) => f.properties.pref))],
        unique: new Set(feats.map((f) => f.properties.id)).size,
      };
    });
    check(`${prefName} で絞ると、その県の点だけが描かれる`,
      filtered.prefs.length === 1 && filtered.prefs[0] === prefName, JSON.stringify(filtered.prefs));
    check(`${prefName} で絞ると描画数がその県の件数になる`, filtered.unique === prefN,
      `描画=${filtered.unique} データ=${prefN}`);
    const shownText = await page.locator(".map-panel [aria-live]").innerText();
    check("表示件数の文言が絞り込みに追随する", shownText.includes(prefN.toLocaleString("ja-JP")), shownText);
    await page.selectOption(".map-panel select", "");
    await idle(page);

    // --- 名称検索 → 詳細 → 似た立地 -----------------------------------------
    console.log("検索・詳細・似た立地");
    // 名前が一意な古墳を選ぶ(同名が 14 件ある「大塚古墳」のようなものを避ける)
    const nameCount = {};
    for (const f of points.features) nameCount[f.properties.name] = (nameCount[f.properties.name] ?? 0) + 1;
    const qIndex = points.features.findIndex((f) => nameCount[f.properties.name] === 1 && f.properties.name.length >= 4);
    const target = points.features[qIndex].properties;
    await page.fill('.map-panel input[type="search"]', target.name);
    const hit = page.locator(".result-list button", { hasText: target.name }).first();
    await hit.scrollIntoViewIfNeeded();
    await hit.click();
    await page.waitForFunction((n) => document.querySelector("#detail-title")?.textContent === n, target.name, { timeout: 15000 })
      .catch(() => {});
    const title = (await page.locator("#detail-title").textContent().catch(() => null))?.trim();
    check("検索結果を押すとその古墳の詳細が開く", title === target.name, `見出し=${title} 期待=${target.name}`);
    const detailText = await page.locator(".detail").innerText().catch(() => "");
    check("詳細に地形の値が出ている", detailText.includes("標高") && /\d/.test(detailText));
    check("詳細に「公開データに無いもの」の説明がある", detailText.includes("公開データに無いもの"));

    // 陽性対照: 押す前は強調が 0 件(押した後の 10 件が「押したから」だと言えるように)
    await idle(page);
    const simBefore = await page.evaluate(async () => {
      const m = window.__kofunMap;
      const data = await m.getSource("similar").getData();
      return {
        data: data.features.length,
        rendered: new Set(m.queryRenderedFeatures({ layers: ["similar-points"] }).map((f) => f.properties.id)).size,
      };
    });
    check("陽性対照: 探す前は似た立地の強調が 0 件", simBefore.data === 0 && simBefore.rendered === 0,
      JSON.stringify(simBefore));

    const button = page.getByRole("button", { name: "立地の似た古墳を探す" });
    await button.scrollIntoViewIfNeeded();
    await button.click();
    await page.waitForFunction(() => document.querySelectorAll(".similar-list li").length > 0, null, { timeout: 30000 })
      .catch(() => {});
    const simItems = await page.locator(".similar-list li").count();
    check("似た立地の一覧が 10 件出る", simItems === 10, `件数=${simItems}`);
    const firstSim = (await page.locator(".similar-list li button").first().innerText().catch(() => "")).trim();
    const wantTop = points.features[fixture.neighbours[qIndex][0]].properties.name;
    check("似た立地の 1 位が Python の照合表と同じ古墳である", firstSim.startsWith(`1. ${wantTop}`),
      `画面=${firstSim.split("\n")[0]} 照合表=${wantTop}`);

    // データは公開 API の getData() で数える。querySourceFeatures は**視野内のタイルの分しか返さず、
    // タイル境界で重複もする**(探針: 視野外で 0 件 / 寄せた後に 10 件の実体を 16 件と返した)。
    // 描画は一意 ID で数える。**検品器は自分では地図を寄せない** —— 寄せるのは画面の責任で、それを検査する。
    await page.waitForFunction(() => !window.__kofunMap.isMoving(), null, { timeout: 15000 }).catch(() => {});
    await idle(page);
    const simAfter = await page.evaluate(async () => {
      const m = window.__kofunMap;
      const data = await m.getSource("similar").getData();
      const b = m.getBounds();
      const inView = data.features.filter(({ geometry: { coordinates: [x, y] } }) =>
        x >= b.getWest() && x <= b.getEast() && y >= b.getSouth() && y <= b.getNorth()).length;
      return {
        data: data.features.length,
        inView,
        rendered: new Set(m.queryRenderedFeatures({ layers: ["similar-points"] }).map((f) => f.properties.id)).size,
      };
    });
    check("似た立地 10 件が強調レイヤーのデータに入る", simAfter.data === 10, JSON.stringify(simAfter));
    check("似た立地 10 件がすべて視野に入る(画面が寄せている)", simAfter.inView === 10, JSON.stringify(simAfter));
    check("似た立地 10 件が実際に描画されている", simAfter.rendered === 10, JSON.stringify(simAfter));
    check("「古墳そのものが似ているという意味ではない」と書いてある",
      (await page.locator(".detail").innerText()).includes("似ているという意味ではありません"));
    const mapSpaces = await strayJapaneseSpaces(page);
    check("/map/(詳細と似た立地を開いた状態)の本文に和文の余計な空白が無い", mapSpaces.length === 0,
      spacesDetail(mapSpaces));

    // 到達: 地図上の点を押しても詳細が開く(座標で撃つので、その点が見えている状態で撃つ)
    const clicked = await page.evaluate(() => {
      const m = window.__kofunMap;
      const f = m.queryRenderedFeatures({ layers: ["kofun-points"] })[0];
      if (!f) return null;
      const p = m.project(f.geometry.coordinates);
      m.fire("click", { lngLat: m.unproject(p), point: p, originalEvent: new MouseEvent("click"), features: [f] });
      return f.properties.name;
    });
    if (clicked) {
      await page.waitForFunction((n) => document.querySelector("#detail-title")?.textContent === n, clicked, { timeout: 15000 })
        .catch(() => {});
    }
    const title2 = (await page.locator("#detail-title").textContent().catch(() => null))?.trim();
    check("地図の点を押すとその古墳の詳細が開く", !!clicked && title2 === clicked, `押した=${clicked} 見出し=${title2}`);

    // --- 陽性対照 G-27: 点のデータを空にすると締切いっぱい待っても 0 のまま ----
    console.log("陽性対照(空データ)");
    const empty = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await empty.route("**/data/kofun-points.geojson", (route) =>
      route.fulfill({ status: 200, contentType: "application/geo+json", body: '{"type":"FeatureCollection","features":[]}' }),
    );
    await empty.goto(`${base}/map/`, { waitUntil: "domcontentloaded" });
    const emptyRender = await waitForRenderedPoints(empty, EMPTY_CONTROL_WAIT_MS);
    check(`陽性対照: 点を空にすると ${EMPTY_CONTROL_WAIT_MS}ms 待っても 0 のまま`, emptyRender.count === 0,
      `描画=${emptyRender.count}`);
    await empty.close();

    // --- 画面幅(HC-078) ----------------------------------------------------
    // --- 立地の探索(T-067) ----------------------------------------------------
    console.log("立地の探索");
    const explore = JSON.parse(await readFile(path.join(OUT, "data", "explore.json"), "utf-8"));
    await page.setViewportSize({ width: 1280, height: 900 });
    const exResp = await page.goto(`${base}/explore/`, { waitUntil: "domcontentloaded" });
    check("/explore/ が HTTP 200 で開く", exResp?.status() === 200, `status=${exResp?.status()}`);
    await page.waitForFunction(
      (n) => document.querySelectorAll(".scatter svg circle[data-i]").length === n,
      explore.ids.length,
      { timeout: RENDER_DEADLINE_MS },
    ).catch(() => {});
    const drawn = await page.evaluate(() => document.querySelectorAll(".scatter svg circle[data-i]").length);
    check("散布図に描いた点の数がデータ件数と一致する", drawn === explore.ids.length, `描画=${drawn} データ=${explore.ids.length}`);

    // G-29: 描いた位置を、SPEC §3.14 の式で配った座標から独立に計算した位置と比べる
    const placement = async () => page.evaluate((xy) => {
      const svg = document.querySelector(".scatter svg");
      const view = Number(svg.dataset.view);
      const pad = Number(svg.dataset.pad);
      const span = view - 2 * pad;
      let worst = 0;
      for (const c of svg.querySelectorAll("circle[data-i]")) {
        const [x, y] = xy[Number(c.dataset.i)];
        const ux = pad + ((x + 1) / 2) * span;
        const uy = pad + (1 - (y + 1) / 2) * span;
        worst = Math.max(worst, Math.abs(Number(c.getAttribute("cx")) - ux), Math.abs(Number(c.getAttribute("cy")) - uy));
      }
      return worst;
    }, explore.xy);
    const worstPlacement = await placement();
    check("G-29 散布図の各点の位置が配った座標と一致する(差 0.01 以下)", worstPlacement <= 0.01, `最大差=${worstPlacement}`);
    await page.evaluate(() => {
      const c = document.querySelector(".scatter svg circle[data-i]");
      c.dataset.saved = c.getAttribute("cx");
      c.setAttribute("cx", String(Number(c.getAttribute("cx")) + 1));
    });
    const shifted = await placement();
    check("陽性対照: 1 点を 1 単位ずらすと位置の検査が検出する", shifted >= 0.99, `ずらした後の最大差=${shifted}`);
    await page.evaluate(() => {
      const c = document.querySelector(".scatter svg circle[data-i]");
      c.setAttribute("cx", c.dataset.saved);
    });

    // G-14: 図の中の要素が viewBox に収まる。getBBox は変換前の箱なので、変換が無いことも確かめる
    const containment = async () => page.evaluate(() => {
      const out = [];
      for (const svg of document.querySelectorAll(".explore-figures svg")) {
        const [vx, vy, vw, vh] = svg.getAttribute("viewBox").split(/\s+/).map(Number);
        let outside = 0;
        let transformed = 0;
        for (const el of svg.querySelectorAll("circle, rect, text, path, line")) {
          if (el.getAttribute("transform")) transformed++;
          const b = el.getBBox();
          if (b.x < vx - 0.01 || b.y < vy - 0.01 || b.x + b.width > vx + vw + 0.01 || b.y + b.height > vy + vh + 0.01) outside++;
        }
        out.push({ label: svg.getAttribute("aria-label").slice(0, 12), outside, transformed });
      }
      return out;
    });
    const boxes = await containment();
    check("G-14 図の要素がすべて viewBox に収まる", boxes.length === 2 && boxes.every((b) => b.outside === 0), JSON.stringify(boxes));
    check("図の要素に変換(transform)が無い(getBBox の前提)", boxes.every((b) => b.transformed === 0), JSON.stringify(boxes));
    await page.evaluate(() => {
      const svg = document.querySelector(".scatter svg");
      const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
      t.setAttribute("x", "-50");
      t.setAttribute("y", "20");
      t.setAttribute("id", "__outside_control");
      t.textContent = "枠外";
      svg.appendChild(t);
    });
    const leakedBoxes = await containment();
    check("陽性対照: 枠外に文字を足すと viewBox の検査が検出する", leakedBoxes[0].outside === 1, JSON.stringify(leakedBoxes));
    await page.evaluate(() => document.getElementById("__outside_control")?.remove());

    // 凡例: 5 クラスの件数の合計が値のある件数に一致する
    const legendCounts = await page.evaluate(() =>
      [...document.querySelectorAll(".legend-steps li .note")].map((n) => Number(n.textContent.replace(/[^\d]/g, ""))),
    );
    const nonNull = explore.metrics.elevation_m.filter((v) => v !== null).length;
    check("凡例が 5 クラスで、件数の合計が値のある件数に一致する",
      legendCounts.length === 5 && legendCounts.reduce((a, b) => a + b, 0) === nonNull, `${legendCounts} 合計≠${nonNull}`);

    // 到達: 点に重ねると、その点の古墳の名前が出る
    const scatterBox = await page.locator(".scatter svg").boundingBox();
    await page.locator(".scatter svg").scrollIntoViewIfNeeded();
    // 変数名は地図の検査の `target` と重ならないようにする(同じ関数の中で const を二重に宣言すると、
    // 読み込みの時点で落ちて検査が一つも走らない)。
    const hoverTarget = await page.evaluate(() => {
      const svg = document.querySelector(".scatter svg");
      const c = svg.querySelector("circle[data-i]");
      const ux = Number(c.getAttribute("cx"));
      const uy = Number(c.getAttribute("cy"));
      const p = new DOMPoint(ux, uy).matrixTransform(svg.getScreenCTM());
      return { i: Number(c.dataset.i), x: p.x, y: p.y, ux, uy, view: Number(svg.dataset.view), pad: Number(svg.dataset.pad) };
    });
    await page.mouse.move(hoverTarget.x, hoverTarget.y);
    const tip = await page.locator(".tooltip strong").textContent({ timeout: 5000 }).catch(() => null);
    // 最寄りの点を出すので、重なっている点では別の古墳になりうる。そこで「その名前を持つ点のどれかが、
    // 重ねた位置から描画単位 14 以内にある」ことを、SPEC §3.14 の式で独立に計算して確かめる。
    const hoverSpan = hoverTarget.view - 2 * hoverTarget.pad;
    const nearby = tip === null ? [] : explore.xy.flatMap(([x, y], i) => {
      if (explore.name[i] !== tip) return [];
      const ux = hoverTarget.pad + ((x + 1) / 2) * hoverSpan;
      const uy = hoverTarget.pad + (1 - (y + 1) / 2) * hoverSpan;
      return Math.hypot(ux - hoverTarget.ux, uy - hoverTarget.uy) <= 14 ? [i] : [];
    });
    check("点に重ねると、重ねた位置の近くの古墳の名前が出る(操作が届いた)", nearby.length > 0,
      `出た名前=${tip} 重ねた点=${explore.name[hoverTarget.i]}`);

    // 範囲選択: ドラッグした枠の中の件数を、枠の属性から SPEC の規則で独立に数えて表示と比べる
    const box = scatterBox ?? (await page.locator(".scatter svg").boundingBox());
    await page.mouse.move(box.x + box.width * 0.3, box.y + box.height * 0.3);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.55, { steps: 8 });
    await page.mouse.up();
    const brushRect = await page.evaluate(() => {
      const r = document.querySelector(".scatter svg rect.brush");
      const svg = document.querySelector(".scatter svg");
      return r ? { x: +r.getAttribute("x"), y: +r.getAttribute("y"), w: +r.getAttribute("width"), h: +r.getAttribute("height"),
        view: +svg.dataset.view, pad: +svg.dataset.pad } : null;
    });
    check("ドラッグすると範囲選択の枠が出る(操作が届いた)", !!brushRect && brushRect.w > 0 && brushRect.h > 0, JSON.stringify(brushRect));
    if (brushRect) {
      const span = brushRect.view - 2 * brushRect.pad;
      const toNorm = (ux, uy) => [((ux - brushRect.pad) / span) * 2 - 1, (1 - (uy - brushRect.pad) / span) * 2 - 1];
      const [x0, y1] = toNorm(brushRect.x, brushRect.y);
      const [x1, y0] = toNorm(brushRect.x + brushRect.w, brushRect.y + brushRect.h);
      const expected = explore.xy.filter(([x, y]) => x0 <= x && x <= x1 && y0 <= y && y <= y1).length;
      const shown = await page.locator("section [aria-live]").textContent().catch(() => "");
      check("範囲選択の件数が、枠から独立に数えた件数と一致する", shown.startsWith(`${expected.toLocaleString("ja-JP")} 件`),
        `表示=${shown} 独立計算=${expected}`);
    }
    await page.getByRole("button", { name: "範囲選択を外す" }).click().catch(() => {});

    // 県の強調: 選んだ県以外の点が灰になる
    const exPrefCounts = {};
    for (const p of explore.pref) if (p) exPrefCounts[p] = (exPrefCounts[p] ?? 0) + 1;
    const [exPref, exPrefN] = Object.entries(exPrefCounts).sort((a, b) => b[1] - a[1])[0];
    await page.selectOption(".filter-row select >> nth=1", exPref);
    await page.waitForFunction((n) => document.querySelector("section [aria-live]")?.textContent?.startsWith(n), exPrefN.toLocaleString("ja-JP"), { timeout: 5000 }).catch(() => {});
    const muted = await page.evaluate(() =>
      [...document.querySelectorAll(".scatter svg circle[data-i]")].filter((c) => c.getAttribute("fill") === "#6f675c").length,
    );
    const nullElev = explore.metrics.elevation_m.filter((v, i) => v === null && explore.pref[i] === exPref).length;
    check(`${exPref} を強調すると、それ以外の点が灰になる`, muted === explore.ids.length - exPrefN + nullElev,
      `灰=${muted} 期待=${explore.ids.length - exPrefN + nullElev}`);
    const exShown = await page.locator("section [aria-live]").textContent().catch(() => "");
    check(`${exPref} を強調すると一覧の件数がその県の件数になる`, exShown.startsWith(`${exPrefN.toLocaleString("ja-JP")} 件`), exShown);
    const radiusAttr = await page.evaluate(() => Number(document.querySelector(".scatter svg").dataset.radius));
    const caption = await page.locator(".scatter figcaption").textContent();
    check("点の半径が SPEC §3.14 の候補(4 / 3 / 2)のどれかで、重なりの実測が添えてある", [4, 3, 2].includes(radiusAttr) && caption.includes("重なりの割合"),
      `半径=${radiusAttr}`);
    console.log(`       (${caption.trim().slice(0, 80)})`);

    // --- 都道府県の比較 ----------------------------------------------------------
    console.log("都道府県の比較");
    await page.goto(`${base}/compare/`, { waitUntil: "domcontentloaded" });
    const compareRows = await page.locator(".data-table tbody tr").count();
    check("比較表の行数が都道府県の数と一致する", compareRows === Object.keys(exPrefCounts).length,
      `行=${compareRows} 県=${Object.keys(exPrefCounts).length}`);
    const firstRow = await page.locator(".data-table tbody tr >> nth=0 >> td").allTextContents();
    check("比較表の先頭が収録件数の最も多い県で、件数が一致する", firstRow[0] === exPref && firstRow[1] === exPrefN.toLocaleString("ja-JP"),
      JSON.stringify(firstRow.slice(0, 2)));
    check("比較表に「実在する古墳の数ではない」と書いてある",
      (await page.locator("body").innerText()).includes("実在する古墳の数ではありません"));

    console.log("画面幅");
    // 320 は SPEC G-15 が指定する最小幅。最初は 360 までしか測っていなかった。
    for (const [w, h] of [[320, 700], [360, 780], [768, 900], [1280, 900], [1680, 1000]]) {
      for (const route of ["/", "/map/", "/explore/", "/compare/", "/sources/", "/methodology/"]) {
        await page.setViewportSize({ width: w, height: h });
        await page.goto(`${base}${route}`, { waitUntil: "domcontentloaded" });
        await page.waitForTimeout(300);
        if (route === "/explore/") {
          // 散布図はデータを読んでから描く。描き終わる前に測ると、読み込み中の小さな画面を測ってしまう
          await page.waitForFunction(() => document.querySelectorAll(".scatter svg circle[data-i]").length > 0, null,
            { timeout: RENDER_DEADLINE_MS }).catch(() => {});
        }
        if (w === 1280 && ["/explore/", "/compare/", "/sources/", "/methodology/"].includes(route)) {
          const spaces = await strayJapaneseSpaces(page);
          check(`${route} の本文に和文の余計な空白が無い`, spaces.length === 0, spacesDetail(spaces));
        }
        const m = await page.evaluate(() => ({
          sw: document.documentElement.scrollWidth,
          cw: document.documentElement.clientWidth,
          sh: document.documentElement.scrollHeight,
        }));
        check(`${route} @${w}px 横に溢れない`, m.sw <= m.cw + 1, `scrollWidth=${m.sw} clientWidth=${m.cw}`);
        check(`${route} @${w}px 縦に伸びすぎない`, m.sh < 16000, `scrollHeight=${m.sh}`);
      }
    }

    // --- フッタ(宛先は描画された DOM で見る。HTML を grep しない) ------------
    console.log("フッタ");
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(`${base}/`, { waitUntil: "domcontentloaded" });

    const homeSpaces = await strayJapaneseSpaces(page);
    check("/ の本文に和文の余計な空白が無い", homeSpaces.length === 0, spacesDetail(homeSpaces));
    // 陽性対照: 撮影で見つけた形そのものを注入すると、この検査が拾う
    await page.evaluate(() => {
      const p = document.createElement("p");
      p.id = "__stray_space_control";
      p.textContent = "その場所の地形と、 立地の似た古墳";
      document.body.appendChild(p);
    });
    const injected = await strayJapaneseSpaces(page);
    check("陽性対照: 和文の余計な空白を注入すると検査が拾う", injected.length === homeSpaces.length + 1,
      `注入前=${homeSpaces.length} 注入後=${injected.length}`);
    await page.evaluate(() => document.getElementById("__stray_space_control")?.remove());
    const footer = await page.evaluate(() => {
      const f = document.querySelector(".fleet-footer");
      return f
        ? { fixed: getComputedStyle(f).position, links: [...f.querySelectorAll("a")].map((a) => [a.innerText.trim(), a.href]) }
        : null;
    });
    check("フッタがある", !!footer);
    if (footer) {
      const href = (label) => footer.links.find(([t]) => t === label)?.[1]?.replace(/\/$/, "");
      check("フッタが下部固定である", footer.fixed === "fixed", footer.fixed);
      check("GitHub がこのリポジトリを指す", href("GitHub") === CANON.github, String(href("GitHub")));
      check("MIT License が LICENSE を指す", href("MIT License") === CANON.license, String(href("MIT License")));
      check("App Menu が本番を指す", href("App Menu") === CANON.appMenu, String(href("App Menu")));
    }

    check("同じ配信元で 4xx/5xx になった資源が無い", badSameOrigin.length === 0, JSON.stringify(badSameOrigin.slice(0, 3)));
    const realErrors = consoleErrors.filter((t) => !/Failed to load resource/.test(t));
    check("コンソールエラーが無い(外部資源の読み込み失敗を除く)", realErrors.length === 0, realErrors.slice(0, 3).join(" | "));

    if (WANT_SHOT) {
      await mkdir(SHOTS, { recursive: true });
      await page.goto(`${base}/map/`, { waitUntil: "domcontentloaded" });
      await waitForRenderedPoints(page, RENDER_DEADLINE_MS);
      // 撮影は嘘をつく(HC-194)。地図は要素単位で撮り、固定フッタは撮影中だけ退ける。
      await page.evaluate(async () => {
        const m = window.__kofunMap;
        m.resize();
        await new Promise((r) => { m.once("idle", r); m.triggerRepaint(); });
        const f = document.querySelector(".fleet-footer");
        if (f) f.style.visibility = "hidden";
      });
      await page.locator(".maplibregl-map").screenshot({ path: path.join(SHOTS, "map.png") });
      console.log("  撮影 → artifacts/screenshots/map.png");
    }
  } finally {
    await browser.close();
    server.close();
  }

  console.log("");
  if (failures.length) {
    console.error(`検品 NG — ${failures.length} 件`);
    for (const f of failures) console.error(`  - ${f}`);
    process.exit(1);
  }
  console.log("検品 OK");
}

main().catch((e) => {
  console.error("検品器そのものが落ちた:", e);
  process.exit(3);
});
