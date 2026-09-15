/**
 * 探索画面の計算(SPEC §3.14)。
 *
 * 範囲選択・中央値・分位の境界は tests/fixtures/explore-reference.json(Python の独立実装)と
 * 照合する(G-30 / G-31)。規則を変えるときは SPEC と Python の両方を直すこと。
 */

export type Rect = { x0: number; x1: number; y0: number; y1: number };

/** 二次元配置の正規化座標の矩形。**辺ちょうどの点を含む**。 */
export function selectInRect(xy: ReadonlyArray<readonly [number, number]>, r: Rect): number[] {
  const out: number[] = [];
  for (let i = 0; i < xy.length; i++) {
    const [x, y] = xy[i];
    if (r.x0 <= x && x <= r.x1 && r.y0 <= y && y <= r.y1) out.push(i);
  }
  return out;
}

function sortedValues(values: ReadonlyArray<number | null>): number[] {
  return values.filter((v): v is number => v !== null).sort((a, b) => a - b);
}

/** 値のある件を昇順に並べ、奇数個なら真ん中、偶数個なら真ん中二つの平均。 */
export function median(values: ReadonlyArray<number | null>): number | null {
  const v = sortedValues(values);
  const n = v.length;
  if (n === 0) return null;
  return n % 2 === 1 ? v[(n - 1) / 2] : (v[n / 2 - 1] + v[n / 2]) / 2;
}

/** 第 j 境界(j = 1..k-1)は v[floor(j·n/k)]。 */
export function quantileBreaks(values: ReadonlyArray<number | null>, k = 5): number[] {
  const v = sortedValues(values);
  const n = v.length;
  if (n < k) return [];
  return Array.from({ length: k - 1 }, (_, j) => v[Math.floor(((j + 1) * n) / k)]);
}

/** 境界ちょうどの値は上のクラス。値なしはクラス無し。 */
export function classOf(value: number | null, breaks: ReadonlyArray<number>): number | null {
  if (value === null) return null;
  let c = 0;
  for (const b of breaks) if (value >= b) c++;
  return c;
}

// --- 描画のスケール(検品器 harness/smoke.mjs はこれを使わず SPEC の式から独立に計算する) ---

export const VIEW = 600;
export const PAD = 24;

/** 正規化座標 [-1, 1] を描画単位へ。y は上を正にする。 */
export function toUser(x: number, y: number): [number, number] {
  const span = VIEW - 2 * PAD;
  return [PAD + ((x + 1) / 2) * span, PAD + (1 - (y + 1) / 2) * span];
}

export function fromUser(ux: number, uy: number): [number, number] {
  const span = VIEW - 2 * PAD;
  return [((ux - PAD) / span) * 2 - 1, (1 - (uy - PAD) / span) * 2 - 1];
}

// --- 指し示し(SPEC §3.14「タップ」) ---

/** 最寄り点として拾う距離の上限(描画単位・この値ちょうどは含まない)。 */
export const NEAREST_MAX = 14;
/** 押してから離すまでの移動がこれ未満(x・y とも)ならタップ。 */
export const TAP_MAX_MOVE = 2;

/** 距離の二乗が最小の点の番号。同じ距離なら番号の小さい方。上限未満に点が無ければ null。 */
export function nearestIndex(
  points: ReadonlyArray<readonly [number, number]>,
  ux: number,
  uy: number,
  maxDistance = NEAREST_MAX,
): number | null {
  let best: number | null = null;
  let bestD = maxDistance * maxDistance;
  for (let i = 0; i < points.length; i++) {
    const d = (points[i][0] - ux) ** 2 + (points[i][1] - uy) ** 2;
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  }
  return best;
}

/** 範囲選択の始点と終点が x・y とも TAP_MAX_MOVE 未満しか離れていなければタップ。 */
export function isTap(b: { ux0: number; uy0: number; ux1: number; uy1: number }): boolean {
  return Math.abs(b.ux1 - b.ux0) < TAP_MAX_MOVE && Math.abs(b.uy1 - b.uy0) < TAP_MAX_MOVE;
}

/**
 * 中心間の距離が直径未満になる相手を持つ点の割合。
 * 距離も半径も同じ比で拡大縮小されるので、描画単位で測れば画面の大きさに依らない。
 */
export function overlapFraction(points: ReadonlyArray<readonly [number, number]>, radius: number): number {
  if (points.length === 0) return 0;
  const cell = 2 * radius;
  const grid = new Map<string, number[]>();
  points.forEach(([x, y], i) => {
    const key = `${Math.floor(x / cell)},${Math.floor(y / cell)}`;
    const bucket = grid.get(key);
    if (bucket) bucket.push(i);
    else grid.set(key, [i]);
  });
  const limit = cell * cell;
  let overlapping = 0;
  points.forEach(([x, y], i) => {
    const cx = Math.floor(x / cell);
    const cy = Math.floor(y / cell);
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        for (const j of grid.get(`${cx + dx},${cy + dy}`) ?? []) {
          if (j === i) continue;
          const [px, py] = points[j];
          if ((px - x) ** 2 + (py - y) ** 2 < limit) {
            overlapping++;
            return;
          }
        }
      }
    }
  });
  return overlapping / points.length;
}

/** SPEC §3.14: 半径 4 から下げ、最初に重なりの割合が上限以下になった半径を採る。どれも超えるなら最小。 */
export function chooseRadius(
  points: ReadonlyArray<readonly [number, number]>,
  candidates: ReadonlyArray<number> = [4, 3, 2],
  limit = 0.5,
): { radius: number; fractions: Record<number, number> } {
  const fractions: Record<number, number> = {};
  for (const r of candidates) {
    fractions[r] = overlapFraction(points, r);
    if (fractions[r] <= limit) return { radius: r, fractions };
  }
  return { radius: candidates[candidates.length - 1], fractions };
}

// --- 配色(SPEC §3.14 で検証済みの値) ---

export const RAMP = ["#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"] as const;
export const SINGLE = "#3987e5";
export const MUTED = "#6f675c";
export const ACCENT = "#c8813a";

export const METRICS = [
  { key: "elevation_m", label: "標高", unit: "m", digits: 1 },
  { key: "slope_deg", label: "傾斜", unit: "度", digits: 1 },
  { key: "openness_500m", label: "周囲より高い度合い", unit: "", digits: 2 },
] as const;
export type MetricKey = (typeof METRICS)[number]["key"];

export type ExploreData = {
  ids: string[];
  name: string[];
  pref: (string | null)[];
  xy: [number, number][];
  lonlat: [number, number][];
  metrics: Record<MetricKey, (number | null)[]>;
};
