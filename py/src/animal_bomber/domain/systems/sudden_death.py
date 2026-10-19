"""延長戦（サドンデス）に入る（原型の enterSuddenDeath）。

TypeScript 版の `mutations/suddenDeath.ts` と同じ。

## 盤面を作り直さず、片付けて使う

いまの盤面の壊せるブロックをすべて消し、爆弾・爆風・アイテム・盤面の物を取り除く。柱の
並びは種によらず決まっているので、壊せるブロックを消せば、作り直した盤面と同じになる。
作り直す場合と違って乱数を引かない（作り直すと、延長戦に入った試合だけ以降の抽選が
ずれる）。

## 1 tick の処理には並べない

延長戦に入るかを決めるのは `systems/round.py` の `judge_round`、ここを呼ぶのは試合を
進める側（`app/session.py` の `GameSession`）。決着のあとの待ちは挟まず、判定と同じ
tick のうちに入る（原型の checkEnd も同じ update のうちに入る）。
"""

from collections.abc import Sequence

from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.events import SimEvent, SuddenDeath, SuddenDeathReason
from animal_bomber.domain.rules.tuning import (
    MAX_BOMBS,
    MAX_POWER,
    MAX_SHOES,
    SPAWN_CELLS,
    SUDDEN_DEATH_HP,
    SUDDEN_DEATH_INVULNERABLE,
    SUDDEN_DEATH_LENGTH,
)
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.player import ALIVE, OUT, PlayerId, PlayerState
from animal_bomber.domain.state.world import WorldState


def enter_sudden_death(
    world: WorldState, players: Sequence[PlayerId], reason: SuddenDeathReason
) -> list[SimEvent]:
    """延長戦に入る。延長戦に入ったことを知らせるイベントを返す。

    加わるプレイヤーは、プレイヤー番号の順に開始位置の表（`SPAWN_CELLS`）の隅へ移る
    （始まった隅とは限らない。原型と同じ）。体力を爆風1回ぶんにして、爆弾・火力・靴を
    上限にし、しばらく無敵にする（決着を急がせるため。`rules/tuning.py` の
    `SUDDEN_DEATH_INVULNERABLE`）。加わらないプレイヤーは退場する。

    Args:
        world: いまの盤面。この関数が書き換える。
        players: 延長戦に加わるプレイヤー。
        reason: 延長戦に入ったわけ。
    """
    world.sudden_death = True
    world.ends_at = Tick(world.now + SUDDEN_DEATH_LENGTH)
    # 走査しながら書き換えないよう、先に集めてから消す。
    soft = [cell for cell, tile in world.board.cells() if tile is Tile.SOFT]
    for cell in soft:
        world.board.put(cell, Tile.EMPTY)
    world.bombs = []
    world.blasts = []
    world.items = []
    world.actors = []
    # 開始位置へ移す前の位置を、知らせるイベントに載せる（歩いた距離を数える側が使う）。
    moved_from = tuple(
        player.position for player in world.players if player.id in players
    )
    # 開始位置は、加わるプレイヤーにプレイヤー番号の順で1つずつ割り当てる。
    slot = 0
    for player in world.players:
        _clear_round_state(player)
        if player.id not in players:
            player.life = OUT
            continue
        spawn = SPAWN_CELLS[slot % len(SPAWN_CELLS)]
        slot += 1
        player.life = ALIVE
        player.position = spawn.center()
        player.hp = SUDDEN_DEATH_HP
        player.max_bombs = MAX_BOMBS
        player.power = MAX_POWER
        player.shoes = MAX_SHOES
        player.invulnerable_until = Tick(world.now + SUDDEN_DEATH_INVULNERABLE)
    # 加わるプレイヤーは、渡された順ではなくプレイヤー番号の順で知らせる。
    joined = tuple(player.id for player in world.players if player.id in players)
    return [SuddenDeath(reason=reason, players=joined, moved_from=moved_from)]


def _clear_round_state(player: PlayerState) -> None:
    """延長戦へ持ち越さない状態を戻す（原型の enterSuddenDeath L4446-4461）。

    ⚠️ 乗っ取り中の振る舞い（`action`）は必ず外す。外さないと、技の続きが開始位置で
    走り、動けないまま固まる（原型の 1.5.1 で直した不具合。原型にも同じ注意書きが
    ある）。後始末は呼ばない（原型も消すだけ）。

    とくぎは印も回数も戻す（原型の L4448）。技のボタンの長押しは数え直す。押したまま
    延長戦に入ると、そこからしきい値ぶん押し続ければ、とくぎがもう一度出る（チキンを
    拾っていれば）。前の tick の入力（`previous_input`）には触らないので、押した瞬間には
    ならない。

    最後に傷を付けた相手（`last_hit_by`）と「勝手に設置」の待ち（`autobomb_wait`）は
    戻さない。原型の enterSuddenDeath も触らない（TypeScript 版と同じ）。
    """
    player.active_bombs = 0
    for kind in EffectKind:
        player.effects.clear(kind)
    player.action = None
    player.has_special = False
    player.special_charges = 0
    player.action_held = Tick(0)
    player.action_fired = False
    player.ability_cooldown = Tick(0)
