"""kofun-atlas-ai の共有コード。

`scripts/` と `ml/` の CLI はここを呼ぶだけの薄い入口にする。
探索で書いた規則を実装へ「写す」のではなく、ここへ昇格させて一箇所に置く(HC-069)。
"""

__all__ = ["dem", "features", "geocode", "geoshape", "ids", "records", "schema", "terrain", "tiles"]
