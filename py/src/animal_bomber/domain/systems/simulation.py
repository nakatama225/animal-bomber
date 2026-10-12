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

1. プレイヤーを乗っ取っている振る舞い（`state/actions.py`）を進め、新しく技を出す
   （`actions.py`）。
   振る舞いを進めた直後に1人ずつ「勝手に設置」の拍に爆弾を置き（`autobomb.py`）、
   新しく技を出すのは全員ぶん置いたあと。振る舞いが位置を決めるので、動く（2.）より
   先に進める。あとから移動の入力を当てると 1 tick ぶん食い違う。勝手に設置を動く前に
   置くのは、原型が効果の時間を進める処理の中で、プレイヤーごとに「技を進める → 勝手に
   設置」と回してから各プレイヤーを動かすため。拍の tick にマスの境目をまたいでも、
   今までいたマスに置く（TypeScript 版と同じ。`actions.py` の説明）
2. 動く（`movement.py`）
3. ボタンの爆弾を置き、導火線を進める（`bomb.py`）。動いてから置く。逆にすると、押した
   tick にマスの境目をまたいだとき、動く前のマスに置かれる（通り抜けの対象から外すのも
   1 tick 遅れるが、位置には効かない）。原型も、ボタンで置くときは動いてから置く
4. 導火線の尽きた爆弾を連鎖ごと爆発させ、爆風の残り時間を進める（`blast.py`）。置いた
   tick にも導火線を進めるので、置いた tick を1つ目と数えて `BOMB_FUSE` 個目の tick に
   爆発する
5. 盤面の物（落とし穴・炎・跳ねる爆弾・撒く本体・焼けた舌）を進める（`actors.py`）。
   爆発のあと。この tick に出た爆風で、跳ねる爆弾が爆発するのも同じ tick になる
6. 足元のアイテムを拾い、溶けきったもの・残る長さを過ぎたものを消す（`items.py`）。
   爆発のあと。逆にすると、この tick の爆風で焼けるはずのアイテムを、同じ tick に
   拾えてしまう
7. 爆風に触れたプレイヤーの体力を減らす（`damage.py`）。爆発のあとなので、この tick に
   出た爆風にも当たる。拾うのより後。逆にすると、被弾して足元へ吐き出したアイテムを、
   同じ tick にそのまま拾い直す
8. 一時的な状態の時間を進める（`effects.py`）。状態の作用を見る処理（1.〜3.）の
   あと。6. でこの tick にかかった状態も、ここで 1 tick 進む（TypeScript 版と同じ）。
   ⚠️ 原型はプレイヤーごとに、技を進める前に減らす。違いが出るのは、原型のプレイヤー
   ごとの処理（技を進める・勝手に設置）の中で、番号の大きいプレイヤーに状態がかかった
   ときだけ。原型はそのフレームのうちにそのプレイヤーの分をもう一度減らすので、この版の
   ほうが 1 tick 遅く切れる。違いは 1 tick なので、並びは変えていない（TypeScript 版と
   同じ）
9. この tick の入力を、次の tick の「押した瞬間」の判定のために、前の入力として残す。
   すべての処理が終わったあとに残す。途中で残すと、そのあとの処理から見て「押した
   瞬間」が消える（いま押した瞬間を見るのは 3. だけなので、4. の前に動かしても結果は
   変わらないが、押した瞬間を見る処理を足すときに崩れないよう最後に置く。技のボタンは
   押した瞬間でなく押し続けた長さで見る）

## 起きたことを戻り値で返す

`step()` は音も鳴らさず、画面にも触らない。この tick に起きたこと（爆発した・拾った・
倒れた、など）を `SimEvent` の list で返すだけで、どう見せるかは受け取った側
（`presentation/presenter.py`）が決める。画面を出さずに試合を回すとき（テスト・強さの
計測）は、受け取らなければよい。そのための設定や「音を鳴らさない」ための分岐を、ルールの
層に持たずに済む。

並びは起きた順（上の処理の順、各処理の中では処理した順）。
"""

from collections.abc import Mapping

from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import SimEvent
from animal_bomber.domain.input.player_input import PlayerInput
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems.actions import step_actions
from animal_bomber.domain.systems.actors import step_actors
from animal_bomber.domain.systems.blast import step_blasts
from animal_bomber.domain.systems.bomb import step_bombs
from animal_bomber.domain.systems.damage import step_damage
from animal_bomber.domain.systems.effects import step_effects
from animal_bomber.domain.systems.items import step_items
from animal_bomber.domain.systems.movement import move_players


def step(world: WorldState, inputs: Mapping[PlayerId, PlayerInput]) -> list[SimEvent]:
    """試合を 1 tick 進め、この tick に起きたことを起きた順に返す。

    Args:
        world: 進める状態。この関数が書き換える。
        inputs: この tick の、プレイヤーごとの入力。出どころ（キーボード・CPU・通信・
            流し直す記録）は問わない。盤面にいる全員の分が要る（`InputGatherer.gather`
            が返すもの）。
    """
    events: list[SimEvent] = []
    events.extend(step_actions(world, inputs))
    move_players(world, inputs)
    events.extend(step_bombs(world, inputs))
    events.extend(step_blasts(world))
    events.extend(step_actors(world))
    events.extend(step_items(world))
    events.extend(step_damage(world))
    step_effects(world)
    _remember_inputs(world, inputs)
    world.now = Tick(world.now + 1)
    return events


def _remember_inputs(world: WorldState, inputs: Mapping[PlayerId, PlayerInput]) -> None:
    """この tick の入力を、全員ぶん前の入力として残す（倒れているプレイヤーも）。"""
    for player in world.players:
        player.previous_input = inputs[player.id]
