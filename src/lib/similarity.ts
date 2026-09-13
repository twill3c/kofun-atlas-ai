/**
 * 立地の似た古墳を探す(SPEC §3.12)。
 *
 * 配る埋め込みは L2 正規化してあるので、余弦類似度は内積に等しい。
 * 並べる規則は Python の照合表(scripts/build_map_assets.py)と**同じ**にする:
 *   類似度の降順 → 同点ならレコードの並び順の昇順 → 自分自身は除く。
 * 配る値は小数 6 桁に丸めてあり、同点は実際に起こる(上位 10 件の中に隣り合う同点 467 組・
 * 2026-09-14 実測)。規則を揃えないと、二実装は正しいまま食い違う(HC-073)。
 */

export type Neighbour = { index: number; score: number };

export function dot(a: ArrayLike<number>, b: ArrayLike<number>): number {
  if (a.length !== b.length) {
    throw new Error(`次元が合わない: ${a.length} != ${b.length}`);
  }
  let s = 0;
  for (let i = 0; i < a.length; i++) s += a[i] * b[i];
  return s;
}

export function topK(
  vectors: ReadonlyArray<ArrayLike<number>>,
  query: number,
  k: number,
): Neighbour[] {
  if (query < 0 || query >= vectors.length) {
    throw new Error(`問い合わせの位置が範囲外: ${query}`);
  }
  const q = vectors[query];
  const all: Neighbour[] = [];
  for (let i = 0; i < vectors.length; i++) {
    if (i === query) continue;
    all.push({ index: i, score: dot(q, vectors[i]) });
  }
  all.sort((a, b) => (a.score !== b.score ? b.score - a.score : a.index - b.index));
  return all.slice(0, k);
}
