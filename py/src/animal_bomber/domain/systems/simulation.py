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
処理ごとに1つのモジュール（`systems/` の下）に分け、`step()` は順に呼ぶだけにしてある。
順は結果を左右するので、並べ替えるときは何が変わるかを確かめる。なぜその順かは、下の
一覧に、`step()` の並びと同じ番号で書く。

1. 動く（`movement.py`）
2. 爆弾を置き、導火線を進める（`bomb.py`）。動いてから置く。逆にすると、押した tick に
   マスの境目をまたいだとき、動く前のマスに置かれる（通り抜けの対象から外すのも
   1 tick 遅れるが、位置には効かない）
3. 導火線の尽きた爆弾を連鎖ごと爆発させ、爆風の残り時間を進める（`blast.py`）。置いた
   tick にも導火線を進めるので、置いた tick を1つ目と数えて `BOMB_FUSE` 個目の tick に
   爆発する
4. この tick の入力を、次の tick の「押した瞬間」の判定のために、前の入力として残す。
   すべての処理が終わったあとに残す。途中で残すと、そのあとの処理から見て「押した
   瞬間」が消える（いま押した瞬間を見るのは 2. だけなので、3. の前に動かしても結果は
   変わらないが、押した瞬間を見る処理を足すときに崩れないよう最後に置く）

アイテムと被弾は、作る段階 3 でこの並びへ足す。
"""

from collections.abc import Mapping

from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems.blast import step_blasts
from animal_bomber.domain.systems.bomb import step_bombs
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
    step_bombs(world, inputs)
    step_blasts(world)
    _remember_inputs(world, inputs)
    world.now = Tick(world.now + 1)


def _remember_inputs(world: WorldState, inputs: Mapping[PlayerId, PlayerInput]) -> None:
    """この tick の入力を、全員ぶん前の入力として残す（倒れているプレイヤーも）。"""
    for player in world.players:
        player.previous_input = inputs[player.id]
