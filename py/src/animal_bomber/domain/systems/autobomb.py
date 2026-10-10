"""「勝手に設置」がかかっているプレイヤーに、拍ごとに爆弾を置かせる。

ボタンで置く爆弾（`systems/bomb.py`）と分けてあるのは、置く時期が違うから。原型は効果の
時間を進める処理の中で全員ぶんの勝手に設置を済ませ、そのあとで各プレイヤーを動かす
（`legacy/animal-bomber.html` の update）。ボタンの爆弾は動いたあとに見る
（humanUpdate）。`simulation.step` はこの処理を動く前に、`bomb.py` を動いたあとに
並べる。拍の tick にマスの境目をまたいでも、置くのは今までいたマスになる
（TypeScript 版の `AutobombSystem` と同じ）。全員ぶんをボタンの爆弾より先に置くので、
同じ tick に置く順と識別子も原型と同じになる（番号の小さいプレイヤーがボタンで置いた
tick に、別のプレイヤーの拍が来たときも）。

⚠️ 段階 5（動物の技）で足すことが3つある。①技の最中に置けるかは技が決める
（TypeScript 版は `PlayerState` の `canPlaceBomb` にまとめ、ボタン・勝手に設置・技で
並べる爆弾がそこを通る）。②技の処理との並べ方を原型に合わせる。原型はプレイヤー
ごとに「そのプレイヤーの技を進める → そのプレイヤーの勝手に設置」と回し、技を始める
のはそのあと（入力の処理）。TypeScript 版はこの形に直した（技の処理が、技を進めた
直後に1人ずつ勝手に設置を呼ぶ。`ActionSystem` の説明）。その形を写す。
③落とし穴にはまっている間は置かない（原型の canPlaceBomb。泣いて動けない間は置ける。
TypeScript 版は落とし穴を、泣くのとは別の状態 'pitfall' で持つ）。
"""

from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import BombPlaced, SimEvent
from animal_bomber.domain.rules.tuning import AUTOBOMB_INTERVAL
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import Life, PlayerState
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems.bomb import place_bomb


def step_autobomb(world: WorldState) -> list[SimEvent]:
    """「勝手に設置」の拍のプレイヤーに、足元へ1つ置かせる。番号の順に置く。

    「爆弾おけない」は見ない。勝手に設置がかかっていると、爆弾おけないにも勝つ
    （`bomb.py` の `_place`）。
    """
    events: list[SimEvent] = []
    for player in world.players:
        if player.life is not Life.ALIVE:
            continue
        # 拍は、このあと置けずに飛ばす場合も進める。原型も、置けなかった拍の次は
        # 1拍あと。
        if not _beat(player):
            continue
        bomb = place_bomb(world, player)
        if bomb is not None:
            events.append(BombPlaced(cell=bomb.cell, owner=bomb.owner))
    return events


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
