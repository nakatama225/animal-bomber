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

from .scenario import play_and_record, play_match, replay

# 台本どおりに 600 tick 進めたあとの要約（`StateHasher.hex` と同じ 8 桁）。
# 2026-10-04 に Python 3.12 で出し、3.11 でも同じ値になることを確かめた。段階 3 で、
# アイテムとプレイヤーごとの体力・無敵の切れる tick・一時的な状態・とくぎの回数・最後に
# 当てたプレイヤーを要約に足し、台本の盤面にアイテムを並べ、向きのボタンを離す間を足し、
# 種を 4649 から 4658 に替えたので、段階 2 の値（89535742）から変わった。
# そのあと、「勝手に設置」を 0.5 秒に1回にして待ちを要約に足したので（台本では2回
# かかる）、c50eb1f2 から変わった。同じときに入れた重なった爆風の持ち主の直しは、この
# 台本の値を変えない（どちらも原型に合わせた。TypeScript 版は 32bf68b）。
GOLDEN = "a599364a"

# ラウンドをまたぐ台本（`play_match`）を 1500 tick 進めたあとの盤面の要約。段階 4 で
# 足した。1ラウンド目は時間切れ、2ラウンド目は 1P の勝ちで試合が決まり、決まった盤面の
# まま止まっている。
GOLDEN_MATCH = "ec70ff0f"


def test_ラウンドをまたぐ台本は_決めておいた要約に行き着く() -> None:
    session = play_match()
    match = session.match
    assert (match.round, match.wins, match.champion, match.finished) == (
        2,
        {0: 1},
        0,
        True,
    )
    assert f"{hash_world(session.world):08x}" == GOLDEN_MATCH


def test_台本どおりの試合は_決めておいた要約に行き着く() -> None:
    played, _ = play_and_record()
    assert f"{hash_world(played):08x}" == GOLDEN


def test_記録を流し直しても_決めておいた要約に行き着く() -> None:
    _, log = play_and_record()
    assert f"{hash_world(replay(log)):08x}" == GOLDEN
