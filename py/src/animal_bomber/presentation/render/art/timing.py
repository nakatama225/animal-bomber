"""tick の数を、原型の描く関数が使う秒に直す。"""

from typing import Final

from animal_bomber.domain.core.tick import TICKS_PER_SECOND

FULL_TURN: Final = 7
"""円を1周描くときの終わりの角度。原型は 2π でなく 7 と書く。

canvas は、始まりと終わりの角度の差が 2π 以上なら1周を描くので、7 でも円になる。
命令の列を原型と突き合わせるため、同じ値を渡す。
"""


def seconds(ticks: float) -> float:
    """tick の数を秒にする。

    原型の記録と同じ値になるよう、`1 / 60` を掛けずに 60 で割る（掛けると最後の桁が
    違うことがある）。盤面の時刻（`world.now`）を渡すと、原型の G.elapsed（ラウンドの
    始まりからの秒）になる。描く時刻（`views/player.py` の `drawn_time`）は、ゲーム
    速度が整数でないとき tick の間の小数になる。
    """
    return ticks / TICKS_PER_SECOND
