/**
 * 詳細ファイルの分割の鍵。scripts/build_map_assets.py の shard_of と同じ規則:
 * `kofun_` を剥がした残りの先頭 2 文字。
 *
 * 言語をまたぐ契約なので、実際に出力された分割ファイル名と突き合わせる検査を置く(HC-190)。
 */
const PREFIX = "kofun_";

export function shardOf(id: string): string {
  if (!id.startsWith(PREFIX)) throw new Error(`ID の形が想定と違う: ${id}`);
  const key = id.slice(PREFIX.length, PREFIX.length + 2);
  if (key.length !== 2) throw new Error(`ID が短すぎて分割できない: ${id}`);
  return key;
}
