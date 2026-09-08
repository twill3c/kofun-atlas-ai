"""T-004 / T-005: 内部 ID の決定論性と丸めの効き方。

期待値の出所: SPEC §8(構想書 §10)の canonical_text 定義。
ID の値そのものは定数で書かない —— 定義から導ける性質だけを固定する。
"""

from __future__ import annotations

import pytest

from kofun_atlas import ids

pytestmark = pytest.mark.unit


def _rec(name="箸墓古墳", pref="奈良県", muni="桜井市", lat=34.539400, lon=135.841200):
    return dict(name=name, prefecture=pref, municipality=muni, lat=lat, lon=lon)


def test_t004_id_is_deterministic_and_wellformed():
    a = ids.kofun_id(**_rec())
    b = ids.kofun_id(**_rec())
    assert a == b
    assert a.startswith("kofun_")
    assert len(a) == len("kofun_") + 10
    assert all(c in "0123456789abcdef" for c in a[6:])


def test_t004_id_recomputes_from_canonical_text():
    """canonical_text を再構成して ID を作り直すと一致する。"""
    rec = _rec()
    text = ids.canonical_text(**rec)
    assert ids.id_from_canonical_text(text) == ids.kofun_id(**rec)


def test_t005_rounding_boundary_positive_control():
    """T-005: 小数第 5 位の違いは同じ ID・第 4 位の違いは別 ID。

    SPEC §8 が round(lat, 4) を定めていることの直接の帰結。
    どちらか一方だけを確かめると、丸めが効いていない実装も、
    丸めが強すぎる実装も通ってしまう。
    """
    base = _rec(lat=34.539400)
    same = _rec(lat=34.5394004)  # 第 7 位のみ差
    diff = _rec(lat=34.539500)  # 第 4 位で差

    assert ids.kofun_id(**base) == ids.kofun_id(**same)
    assert ids.kofun_id(**base) != ids.kofun_id(**diff)


def test_t004_name_is_nfkc_normalized():
    """全角・半角の揺れが同じ ID に落ちる(構想書 §12.1 の名称正規化)。"""
    a = ids.kofun_id(**_rec(name="ＡＢ古墳"))
    b = ids.kofun_id(**_rec(name="AB古墳"))
    assert a == b
