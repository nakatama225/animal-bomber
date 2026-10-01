"""試合を 1 tick 進める。

## `step()` は経過時間を受け取らない

この実装でいちばん目に見える設計の判断。原型の `update(dt)` は前のフレームからの経過
秒数を受け取り、そこに倍速のつまみの値まで掛かっていた。その結果、1回の描画で内部の処理が
何回まわるかが実行環境によって変わった。

`step()` を1回呼ぶと 1 tick 進む。速さは `step()` を**何回呼ぶか**で表す。倍速は呼ぶ
回数を増やすだけ、一時停止は呼ばないだけになる。

クラスにせず関数にしたのは、持つ状態が無いため。状態はすべて `WorldState` にある。

## 処理を並べる順

下の `step()` の中の並びが、そのまま「1 tick の中で何が先に起きるか」の一覧になる。
順は結果を左右するので、並べ替えるときは何が変わるかを確かめる。いまは移動だけで、
爆弾・爆風・アイテム・被弾は、作る段階でこの並びへ足す。
"""

from collections.abc import Mapping

from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems.movement import move_players


def step(world: WorldState, inputs: Mapping[PlayerId, PlayerInput]) -> None:
    """試合を 1 tick 進める。

    Args:
        world: 進める状態。この関数が書き換える。
        inputs: この tick の、プレイヤーごとの入力。出どころ（キーボード・CPU・通信・
            流し直す記録）は問わない。盤面にいる全員の分が要る（`InputGatherer.gather`
            が返すもの）。
    """
    move_players(world, inputs)
    world.now = Tick(world.now + 1)
