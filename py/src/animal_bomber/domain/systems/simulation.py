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

並びは原型の update（`legacy/animal-bomber.html`）と同じ。1. と 2. は、プレイヤーごとに
いくつかの処理を済ませてから次のプレイヤーへ進む輪になっている（原型もそう回す。
TypeScript 版の `Simulation` と同じ）。

1. プレイヤーごとに：焼けた舌を戻す（`actors.py` の `step_owned_actors`）→ 一時的な
   状態の時間を減らす（`effects.py`）→ 乗っ取り中の振る舞いを進める（`actions.py` の
   `advance_for`）→ 「勝手に設置」の拍を見る（`autobomb.py`）。原型の「効果
   タイマー」の輪。振る舞いが位置を決めるので、動く（2.）より先に進める。あとから移動
   の入力を当てると 1 tick ぶん食い違う。状態の時間を技の前に減らすので、番号の小さい
   プレイヤーの技で番号の大きいプレイヤーに状態がかかると、その tick のうちに1回減る
   （`effects.py` の説明）。焼けた舌が戻るのは振る舞いを進める前なので、戻る tick に
   伸びる舌は、戻った長さまで伸びる。拍の tick にマスの境目をまたいでも、今までいた
   マスに置く（`autobomb.py`）
2. プレイヤーごとに：動く（`movement.py`）→ ボタンの爆弾を置く（`bomb.py`）→ 技を
   始める（`actions.py` の `watch_for`）→ 足元のアイテムを拾う（`items.py`）。原型の
   「入力 / AI」の輪。動いてから置くので、押した tick にマスの境目をまたいだら、動いた
   あとのマスに置く。動いてから技を始めるので、技が出る tick に向きを押せば、押した
   向きへ出る。1人ずつ済ませるので、番号の小さいプレイヤーが置いた爆弾は、同じ tick
   にあとから動くプレイヤーの壁になる
3. 爆弾のマスから出たプレイヤーを通り抜けの対象から外し（`bomb.py`）、盤面の物（落とし
   穴・炎・撒く本体・跳ねる爆弾）を `actor_turn` の順に進める（`actors.py`）。拾った
   あとに落とし穴に落ちる（穴が滑りを消すので、穴の上のバナナを踏んでも、穴を抜けた
   あと滑らない）。跳ねる爆弾の爆発は、ふつうの爆弾より先
4. 溶けきったもの・残る長さを過ぎたアイテムを消す（`items.py` の `remove_expired`）
5. 導火線を進め（`bomb.py`）、尽きた爆弾を連鎖ごと爆発させる（`blast.py`）。置いた
   tick にも導火線を進めるので、置いた tick を1つ目と数えて `BOMB_FUSE` 個目の tick
   に爆発する。拾うのは爆発より前（2.）なので、爆発する tick に踏み込んだアイテムは、
   焼ける前に拾える
6. 爆風の残り時間を進める（`blast.py`）
7. 爆風に触れたプレイヤーの体力を減らし（`damage.py`）、そのあと、爆風に触れた振る舞い
   （伸びている舌）を終える（`actions.py` の `after_damage`）。この tick に出た爆風
   にも当たり、舌もこの tick のうちに焼き切れる。被弾して足元へ吐き出したアイテムを
   拾うのは、次の tick（2.）
8. この tick の入力を、次の tick の「押した瞬間」の判定のために、前の入力として残す。
   すべての処理が終わったあとに残す。途中で残すと、そのあとの処理から見て「押した
   瞬間」が消える（いま押した瞬間を見るのは 2. の爆弾だけだが、押した瞬間を見る処理
   を足すときに崩れないよう最後に置く。技のボタンは押した瞬間でなく押し続けた長さで
   見る）

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
from animal_bomber.domain.systems.actions import advance_for, after_damage, watch_for
from animal_bomber.domain.systems.actors import step_actors, step_owned_actors
from animal_bomber.domain.systems.autobomb import autobomb_for
from animal_bomber.domain.systems.blast import detonate_expired, expire_blasts
from animal_bomber.domain.systems.bomb import (
    advance_fuses,
    place_for,
    release_pass_through,
)
from animal_bomber.domain.systems.damage import step_damage
from animal_bomber.domain.systems.effects import advance_effects_for
from animal_bomber.domain.systems.items import pick_up_for, remove_expired
from animal_bomber.domain.systems.movement import move_player


def step(world: WorldState, inputs: Mapping[PlayerId, PlayerInput]) -> list[SimEvent]:
    """試合を 1 tick 進め、この tick に起きたことを起きた順に返す。

    Args:
        world: 進める状態。この関数が書き換える。
        inputs: この tick の、プレイヤーごとの入力。出どころ（キーボード・CPU・通信・
            流し直す記録）は問わない。盤面にいる全員の分が要る（`InputGatherer.gather`
            が返すもの）。
    """
    events: list[SimEvent] = []
    # 1.
    advanced: list[PlayerId] = []
    for player in world.players:
        events.extend(step_owned_actors(world, player))
        advance_effects_for(player)
        advanced_events, did_advance = advance_for(world, player)
        if did_advance:
            advanced.append(player.id)
        events.extend(advanced_events)
        events.extend(autobomb_for(world, player))
    # 2. この tick に振る舞いを進めたプレイヤーは、新しく始めない（`actions.py`）。
    for player in world.players:
        player_input = inputs[player.id]
        move_player(world, player, player_input)
        events.extend(place_for(world, player, player_input))
        if player.id not in advanced:
            events.extend(watch_for(world, player, player_input))
        events.extend(pick_up_for(world, player))
    # 3.
    release_pass_through(world)
    events.extend(step_actors(world))
    # 4.〜6.
    events.extend(remove_expired(world))
    advance_fuses(world)
    events.extend(detonate_expired(world))
    expire_blasts(world)
    # 7.
    events.extend(step_damage(world))
    events.extend(after_damage(world))
    # 8.
    _remember_inputs(world, inputs)
    world.now = Tick(world.now + 1)
    return events


def _remember_inputs(world: WorldState, inputs: Mapping[PlayerId, PlayerInput]) -> None:
    """この tick の入力を、全員ぶん前の入力として残す（倒れているプレイヤーも）。"""
    for player in world.players:
        player.previous_input = inputs[player.id]
