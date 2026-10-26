"""盤面に置かれた爆弾と、爆風の乗っている1マス。

どちらも `eq=False` にして、同じものかを中身でなく実体で比べる（`world.bombs.remove`
や `in` が、中身の同じ別の爆弾を取り違えないように）。⚠️ 実体で比べるものの hash は
番地から作られるので、set や dict の鍵に入れて順に取り出さない。
"""

from dataclasses import dataclass, field

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.state.player import PlayerId


@dataclass(slots=True, eq=False)
class Bomb:
    """盤面に置かれた爆弾。"""

    id: EntityId
    cell: Cell
    owner: PlayerId
    """置いたプレイヤー。爆発したら、このプレイヤーの盤面に出ている爆弾の数が減る。"""
    power: int
    """爆風が各方向へ届くマス数。

    置いた時点の、置いたプレイヤーの火力で決まり、あとから変わらない（置いたあとで
    アイテムを取っても、もう置いた爆弾の爆風は伸びない）。
    """
    fuse: Tick
    """爆発までの残り tick。"""
    pass_through: set[PlayerId] = field(default_factory=set)
    """置かれた瞬間に体の中心がこのマスにあり、まだそこから出ていないプレイヤー。

    このプレイヤーたちにとっては、このマスは通れる（`query/board.py` の
    `is_solid_for`）。置いたプレイヤー自身だけでなく、そのとき体の中心がこのマスに
    あった全員を入れる（TypeScript 版と同じ）。原型は、体がこのマスにかかっている
    全員を入れる（overlapsTile）。違いが出るのは `is_solid_for` の答えだけで、移動の
    結果は変わらない（下の ⚠️）。原型は、ほかのプレイヤーに足元へ爆弾を置かれた
    プレイヤーが動けなくなる不具合の修正で、置いたプレイヤー以外も入れる形にした。

    ⚠️ この版の移動の結果には影響しない。移動の当たり判定（`systems/movement.py` の
    `collides`）は体の重なっているマスを見ない。そして、ここに入っているプレイヤーの
    体は、1 tick の移動（最大 0.157 マス）が体の半径（0.36）より短いので、その tick
    のあいだ爆弾のマスにかかったままでいる。だから誰が入っていても位置は変わらない。
    影響が出始めるのは、通れるかを `is_solid_for` に尋ねる処理（段階 5・6 の動物の技と
    CPU）を足してから。

    中にいるかを見る・外す・数える・並べ替えてから取り出す（状態の要約）だけに使う。
    並べ替えずに順に取り出さない。
    """
    chained: bool = False
    """連鎖の待ち行列に積まれたか。同じ爆弾を二度積まないための印。

    導火線が尽きて爆発する、連鎖の始めの1つにも立てる。積まれた爆弾はその tick の
    うちに盤面から取り除かれるので、tick の終わりに盤面にある爆弾ではいつも False。
    それでも状態と要約に入れておくのは、TypeScript 版と状態の形を揃え、
    `tests/systems/test_simulation_ts.py` で比べるため。
    """


@dataclass(slots=True, eq=False)
class Blast:
    """爆風が乗っている1マス。"""

    id: EntityId
    cell: Cell
    owner: PlayerId
    """この爆風を出した爆弾を置いたプレイヤー。誰に倒されたかの判定に使う（段階 3）。"""
    is_center: bool
    """爆弾が置かれていたマスか。まわりへ伸びたマスは False。"""
    remaining: Tick
    """消えるまでの残り tick。"""
