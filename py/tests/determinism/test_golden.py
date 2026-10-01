"""台本どおりの試合が、決めておいた状態の要約に行き着くことの検査（固定値）。

リプレイの検査（`test_replay.py`）は、同じプロセスの中で2回走らせて比べる。それでは、
Python の版や実行する機械が変わったときに結果が変わることを捕まえられない。ここでは、
一度出した要約をコードに書いておき、毎回それと比べる。検査（`tools/verify.sh`）は
pytest を 3.12 で走らせたあと、3.11 でもう一度走らせる（`uv run --isolated --python 3.11
pytest` の行）ので、版で結果が変わればどちらかで失敗する。

そのため、リプレイの保存に Python の版を書いておき、違えば流し直しを断る仕組みは
作らない。版で結果が変わるなら、それはルールの層の誤り（版で値が変わる計算を使って
いる）で、ここで見つけて直す。

⚠️ ルールを変えて試合の結果が変わったときは、ここも失敗する。変わることが意図どおり
なら、新しい値を出して書き換え、なぜ変わったかをコミットに書く。意図していなければ、
値を書き換えずに原因を探す。
"""

from animal_bomber.domain.state.world import hash_world

from .scenario import play_and_record, replay

# 台本どおりに 600 tick 進めたあとの要約（`StateHasher.hex` と同じ 8 桁）。
# 2026-10-02 に Python 3.12 で出し、3.11 でも同じ値になることを確かめた。
GOLDEN = "8202cc6e"


def test_台本どおりの試合は_決めておいた要約に行き着く() -> None:
    played, _ = play_and_record()
    assert f"{hash_world(played):08x}" == GOLDEN


def test_記録を流し直しても_決めておいた要約に行き着く() -> None:
    _, log = play_and_record()
    assert f"{hash_world(replay(log)):08x}" == GOLDEN
