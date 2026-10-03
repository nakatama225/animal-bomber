"""かかっている一時的な状態の時間を進める。

状態そのものの作用（滑る・動けない・爆弾を置けない）は、それぞれの処理が自分の受け持ち
の中で見る（移動は `movement.py`、置くのは `bomb.py`）。ここは時間を進めるだけ。

分けてあるのは、作用を1か所に集めると「移動のことも爆弾のことも知っている大きな
処理」ができてしまうため。時間の進め方は全部の状態に共通で、作用は受け持ちごとに違う。
"""

from animal_bomber.domain.state.world import WorldState


def step_effects(world: WorldState) -> None:
    """全員の一時的な状態を 1 tick 進め、切れたものを外す（倒れているプレイヤーも）。"""
    for player in world.players:
        player.effects.advance()
