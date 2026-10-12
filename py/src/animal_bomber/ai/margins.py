"""CPU の判断に使う余裕の長さ。

値は原型から持ってきた（秒を tick に直してある。TypeScript 版の `margins.ts` と同じ）。
どれも「このくらい前から避ける」という慎重さの度合いで、大きくすれば安全側に倒れるが、
逃げ道や通り道が見つかりにくくなる。
"""

from typing import Final

from animal_bomber.domain.core.tick import seconds_to_ticks
from animal_bomber.domain.rules.tuning import BOMB_FUSE

ROUTE_AVOID: Final = seconds_to_ticks(1.6)
"""歩き回るとき、この時間以内に燃えるマスは通らない。

アイテムを拾いに行く・相手を追う・ブロックを壊しに行く・うろつく、のすべてで同じ値。
"""

FLEE_AVOID: Final = seconds_to_ticks(0.35)
"""逃げるとき、この時間以内に燃えるマスは通らない（歩き回るときより小さい）。"""

FALLBACK_MARGIN: Final = seconds_to_ticks(0.6)
"""完全に安全なマスが見つからないとき、いまより少なくともこれだけ長く持つマスへ逃げる。

⚠️ そこはまだ爆風の中。弱い CPU だけが使う妥協。
"""

ESCAPE_MARGIN: Final = seconds_to_ticks(0.7)
"""爆弾を置いたあと逃げ切れるかを見るとき、導火線からこれだけ引いた時間で逃げ切れることを求める。"""

ESCAPE_SPEED_RATIO: Final = 0.7
"""逃げ切れるかの見積もりで、自分の速さに掛ける倍率。

曲がり角での減速や、通路の中央への寄せのぶん、実際には最高の速さでは走れない。
"""

SAME_SPOT_BAN: Final = seconds_to_ticks(4.5)
"""同じマスに爆弾を置き直さない期間。

⛔ これが無いと「置く → 自分の爆風から逃げて離れる → 爆発が終わると同じマスへ戻って
また置く」を延々と繰り返し、3マスの範囲から出られなくなる。原型の実測で、1秒あたり
5.1 回この往復をしていた。
"""

UNSAFE_SPOT_BAN: Final = seconds_to_ticks(0.8)
"""置いたら逃げ切れない場所だと分かったあと、爆弾を狙わない期間。"""

OUT_OF_BOMBS_BAN: Final = seconds_to_ticks(0.35)
"""手持ちの爆弾を出し切っているとき、爆弾を狙わない期間。

これは「場所が悪い」のではなく「今は待つ」だけなので短い。長くすると置かなくなる。
原型で、往復 288 回を測って決めた値。
"""

SKILL_RETRY: Final = seconds_to_ticks(0.4)
"""とくぎの抽選に外れたあと、次に抽選するまで。"""

SHARP_THINK_SECONDS: Final = 0.03
"""危ないときに判断を詰める場合の間隔（秒。揺らぎを掛けてから tick にする）。"""

BLIND_MIN_SECONDS: Final = 0.35
"""弱い CPU が危険に気づかない長さの最短（秒）。"""

BLIND_SPREAD_SECONDS: Final = 0.5
"""弱い CPU が危険に気づかない長さの揺れ幅（秒）。"""

NOTICE_WITHIN: Final = BOMB_FUSE + seconds_to_ticks(0.2)
"""立っているマスに、この tick 数より早く爆風が届くなら「危ない」とみなす。

原型 cpuUpdate の `danger[ty][tx] < BOMB_FUSE + 0.2`。どの爆弾も導火線より長くは持たない
ので、爆風の届くマスはどれも危ない。
"""
