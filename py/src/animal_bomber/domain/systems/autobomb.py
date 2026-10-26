"""「勝手に設置」がかかっているプレイヤーに、拍ごとに爆弾を置かせる。

ボタンで置く爆弾（`systems/bomb.py`）と分けてあるのは、置く時期が違うから。原型は効果の
時間を進める処理の中で、プレイヤーごとに「そのプレイヤーの技を進める → そのプレイヤーの
勝手に設置」の順に処理し、そのあとで各プレイヤーを入力で動かして技を始める
（`legacy/animal-bomber.html` の update）。ボタンの爆弾は動いたあとに見る
（humanUpdate）。

この処理は技の処理（`systems/actions.py`）から、技を進めた直後に1人ずつ呼ばれる。新しく
技を始めるのと、入力で動く（`systems/movement.py`）のは、全員ぶんの勝手に設置のあと。
そのため、

- 拍の tick にマスの境目をまたいでも、置くのは今までいたマス
- 技を始める tick に拍が来たら、置いてから技を始める
- 番号の大きいプレイヤーの技が拍のプレイヤーを押しのけるときは、置いてから押しのける
  （同じ tick にその爆弾を起こすこともある）。番号の小さいプレイヤーの技なら、押しのけた
  あとのマスに置く

が原型と同じになる（TypeScript 版の `AutobombSystem` と同じ）。全員ぶんをボタンの爆弾
より先に置くので、同じ tick に置く順と識別子も原型と同じ（番号の小さいプレイヤーが
ボタンで置いた tick に、別のプレイヤーの拍が来たときも）。
"""

from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import BombPlaced, SimEvent
from animal_bomber.domain.rules.tuning import AUTOBOMB_INTERVAL
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import PlayerState, can_place_bomb, is_alive
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems.bomb import place_bomb


def autobomb_for(world: WorldState, player: PlayerState) -> list[SimEvent]:
    """1人ぶん。拍が来ていて置ける状態なら、足元に1つ置かせる。

    落とし穴にはまっている間と、置けない振る舞いの最中は置かない（`can_place_bomb`）。
    「爆弾おけない」には止められない。勝手に設置がかかっている間は、そちらが勝つ。
    """
    if not is_alive(player):
        return []
    # 拍は、このあと置けずに飛ばす場合も進める。原型も、置けなかった拍の次は
    # 1拍あと。
    if not _beat(player):
        return []
    if not can_place_bomb(player):
        return []
    bomb = place_bomb(world, player)
    if bomb is None:
        return []
    return [BombPlaced(cell=bomb.cell, owner=bomb.owner)]


def _beat(player: PlayerState) -> bool:
    """置こうとする拍か。かかっている間だけ、待ちを1 tick 進める。

    前にかかったときの待ちが残っていなければ、かかった次の tick が最初の拍になり、
    そのあとは `AUTOBOMB_INTERVAL` ごと。待ちを 0 に戻すのはラウンドの始まりだけ。
    """
    if not player.effects.has(EffectKind.AUTOBOMB):
        return False
    wait = max(0, player.autobomb_wait - 1)
    if wait > 0:
        player.autobomb_wait = Tick(wait)
        return False
    player.autobomb_wait = AUTOBOMB_INTERVAL
    return True
