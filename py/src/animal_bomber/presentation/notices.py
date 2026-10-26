"""画面の上に短く出す通知の文（原型の `toast` の 22 種）。

文は原型（`legacy/animal-bomber.html`）の `toast`・`flash` の呼び出しから逐語で
写した。差し込む所は `{name}` のような `str.format` の欄にしてある（原型の `${…}`）。
写し違いは `tests/presentation/test_notices.py` が、欄に原型の `${…}` を入れて、原型の
ファイルの中にそのまま見つかるかで見る。

試合の中の 17 種は `presenter.py` が出す。

- アイテム：バナナ・たまねぎ・チキン・うんこ（L1609・L1613・L1619・L1633）
- 葱ボン：外周へ回った・入れ替わった・外周が閉じた（L2269・L2354・L2362）
- 舌：焼き切れた・根元まで焼けた舌を出そうとした・1マス戻った（L2488・L2498・L4307）
- 穴ととくぎ：穴を掘り終えた・穴にはまった・とくぎを使った（L2575・L2597・L2611）
- 体当たりと鼻水：吸い込んだ・押しつけた・鼻水で消した（L2818・L2880・L3036）
- 延長戦に入った（L4463）

試合の外の5種（パッドが対応していない・パッドを認識した・中継との接続が切れた・
ホストが抜けた・CPU が引き継いだ。L3498・L3527・L3735・L3787・L3793）のうち、パッドの
2種と CPU が引き継いだ通知は画面の流れを実行する側（`app/shell.py` の `Shell`）が、
中継との接続が切れた・ホストが抜けたの2種は通信対戦の局面を画面へ反映する側
（`app/lan_flow.py` の `LanFlow`）が出す。ホストが抜けた通知は、ロビーでホストが
抜けたときだけ出す（この版の通信対戦は、試合の最中にホストが抜けても CPU が引き継いで
続く）。

呼び方は、L2354 だけが原型の `label`（人間は「1P」、CPU は動物の名前。通信対戦で抜けて
CPU に替わったプレイヤーは、人間だったときの「2P」のまま。`hud/roster.py` の
`label_of`）で、ほかは動物の名前（原型の `p.animal.name`）。どちらで呼ぶかは出す側
（`presenter.py`）が決める。
"""

from typing import Final, assert_never

from animal_bomber.domain.core.tick import TICKS_PER_SECOND
from animal_bomber.domain.events import SuddenDeathReason
from animal_bomber.domain.rules.tuning import (
    MAX_BOMBS,
    MAX_POWER,
    MAX_SHOES,
    SUDDEN_DEATH_HP,
    SUDDEN_DEATH_LENGTH,
)
from animal_bomber.presentation.emoji import HOLE
from animal_bomber.presentation.menu.choices import hits_for_hp

DOUBLED: Final = "（2倍！）"
"""効果が2倍になる動物の、アイテムの通知の末尾（原型の `bonus`。L1603）。"""

SLIPPED: Final = "🍌 {name} すべる！{doubled}"
"""バナナで滑り始めた（原型 L1609）。`doubled` は `DOUBLED` か空。"""

CRIED: Final = "🧅 {name} 涙で動けない！{doubled}"
"""たまねぎで泣き始めた（原型 L1613）。"""

CHICKEN: Final = "🍗 {name} とくぎ「{special}」{times}！"
"""チキンを拾った（原型 L1619）。`times` は `CHICKEN_TIMES` か空。"""

CHICKEN_TIMES: Final = " ×{times}"
"""チキン1つで2回ぶん溜まる動物の、回数の書き方（原型 L1619 の `` ` ×${M}` ``）。"""

POOPED: Final = "💩 {name} {label}！{doubled}"
"""うんこを踏んで状態がかかった（原型 L1633）。`label` は状態の名前。"""

TO_LANE: Final = "🌿 {name} は葱ボンへ！ 外周から葱を撃って復活をねらえ"
"""盤面で倒れて外周へ回った（原型 L2269。人間のプレイヤーだけに出す）。"""

REVIVED: Final = "🌿 {shooter} 復活！ {victim} が葱ボンへ"
"""葱が当たって入れ替わった（原型 L2354）。呼び方は原型の `label`。"""

LANES_CLOSED: Final = "🌿 葱ボン 退場！ もう復活できない"
"""残り時間が短くなって外周が閉じた（原型 L2362）。"""

TONGUE_BURNT: Final = "👅🔥 {name} の舌が焼き切れた！このラウンドは {reach}マスまで"
"""伸ばしていた舌が爆風に触れた（原型 L2488）。`reach` は焼けたあとの長さ。"""

TONGUE_GONE: Final = "👅🔥 {name} の舌は焼け落ちてる（{seconds}秒で1マス戻る）"
"""根元まで焼けた舌を出そうとした（原型 L2498）。"""

TONGUE_REGROWN: Final = "👅 {name} の舌が1マス回復（{reach}マス）"
"""焼けた舌が1マス戻った（原型 L4307）。`reach` は戻ったあとの長さ。"""

PIT_DUG: Final = HOLE + " {name} 落とし穴をしかけた"
"""穴を掘り終えた（原型 L2575）。"""

PIT_FALLEN: Final = HOLE + " {name} 落とし穴！ {seconds}秒うごけない"
"""穴にはまった（原型 L2597）。"""

SPECIAL_USED: Final = "{emoji} {name} {special}！"
"""とくぎを使った（原型 L2611）。`emoji` と `special` は、とくぎの絵文字と名前。"""

SWEPT: Final = "{emoji} {name} 突進で {label} を吸い込んだ！"
"""体当たりで進む間に、通り道の良いアイテムを取った（原型 L2818）。"""

PUSHED: Final = "💥 {name} が {target} に {count}個 ぶつけた！"
"""体当たりで、抱えていた悪いアイテムを相手に押しつけた（原型 L2880）。"""

SPRAYED: Final = "💧 {name} 鼻水で {what}！"
"""鼻水で何か消した（原型 L3036）。

`what` は `DOUSED` と `WASHED` を「・」でつないだもの。
"""

DOUSED: Final = "爆弾{count}個の火を消した"
"""鼻水で消した爆弾の数（原型 L3034）。"""

WASHED: Final = "うんこ{count}個を流した"
"""鼻水で流したうんこの数（原型 L3035）。"""

SUDDEN_DEATH: Final = (
    "⚡ サドンデス！（{reason}） 全員HP{hp}・"
    "💣{bombs}・🔥{power}・👟{shoes}・{seconds}秒"
)
"""延長戦に入った（原型 L4463）。"""

ALL_DOWN: Final = "同時にやられた"
"""残っていた全員が同じ tick に倒れた、という理由（原型 L4419・L4420）。

延長戦の通知と、引き分けの幕（`hud/banner.py`）で使う。
"""

TIME_UP: Final = "時間切れ"
"""時間切れで2人以上残った、という理由（原型 L4429・L4430）。"""

PAD_UNSUPPORTED: Final = "🎮 このコントローラーには対応していません（{pad}）"
"""ボタンの並びが標準でないパッドをつないだ（原型 L3498。1回だけ出す）。"""

PAD_FOUND: Final = "🎮 コントローラーを認識しました"
"""パッドを初めて認識した（原型 L3527。1回だけ出す）。"""

SERVER_LOST: Final = "サーバとの接続が切れました"
"""中継との接続が切れた（原型 L3735）。"""

HOST_LOST: Final = "ホストとの接続が切れました"
"""ホストが抜けた（原型 L3787）。"""

CPU_TOOK_OVER: Final = "{name} の回線が切れた → CPU が引き継ぐ"
"""抜けたプレイヤーを CPU が引き継いだ（原型 L3793）。"""


def doubled(times: int) -> str:
    """アイテムの通知の末尾。効果の倍率 `times` が 1 より大きければ付ける。"""
    return DOUBLED if times > 1 else ""


def slipped(name: str, times: int) -> str:
    """バナナで滑り始めた通知。`times` は効果がかかる側の動物の、効果の倍率。"""
    return SLIPPED.format(name=name, doubled=doubled(times))


def cried(name: str, times: int) -> str:
    """たまねぎで泣き始めた通知。"""
    return CRIED.format(name=name, doubled=doubled(times))


def chicken_taken(name: str, special: str, times: int) -> str:
    """チキンを拾った通知。`special` はとくぎの名前、`times` は1つで溜まる回数。"""
    count = CHICKEN_TIMES.format(times=times) if times > 1 else ""
    return CHICKEN.format(name=name, special=special, times=count)


def pooped(name: str, label: str, times: int) -> str:
    """うんこを踏んで状態がかかった通知。"""
    return POOPED.format(name=name, label=label, doubled=doubled(times))


def to_lane(name: str) -> str:
    """盤面で倒れて外周へ回った通知。"""
    return TO_LANE.format(name=name)


def revived(shooter: str, victim: str) -> str:
    """葱が当たって入れ替わった通知。呼び方は原型の `label`（`roster.label_of`）。"""
    return REVIVED.format(shooter=shooter, victim=victim)


def tongue_burnt(name: str, reach: int) -> str:
    """舌が焼き切れた通知。"""
    return TONGUE_BURNT.format(name=name, reach=reach)


def tongue_gone(name: str, wait: int) -> str:
    """根元まで焼けた舌を出そうとした通知。`wait` は1マス戻るまでの残り（tick）。

    秒は切り上げる（原型の `Math.ceil(p.tongueRegen)`）。
    """
    return TONGUE_GONE.format(name=name, seconds=ceil_seconds(wait))


def tongue_regrown(name: str, reach: int) -> str:
    """焼けた舌が1マス戻った通知。"""
    return TONGUE_REGROWN.format(name=name, reach=reach)


def pit_dug(name: str) -> str:
    """穴を掘り終えた通知。"""
    return PIT_DUG.format(name=name)


def pit_fallen(name: str, hold: int) -> str:
    """穴にはまった通知。`hold` は動けない長さ（tick）。"""
    return PIT_FALLEN.format(name=name, seconds=ceil_seconds(hold))


def special_used(emoji: str, name: str, special: str) -> str:
    """とくぎを使った通知。"""
    return SPECIAL_USED.format(emoji=emoji, name=name, special=special)


def swept(emoji: str, name: str, label: str) -> str:
    """体当たりで進む間に良いアイテムを取った通知（`emoji`・`label` はアイテムの）。"""
    return SWEPT.format(emoji=emoji, name=name, label=label)


def pushed(name: str, target: str, count: int) -> str:
    """抱えていた悪いアイテムを相手に押しつけた通知。"""
    return PUSHED.format(name=name, target=target, count=count)


def sprayed(name: str, doused: int, washed: int) -> str | None:
    """鼻水で何か消した通知。何も消さなければ None（原型も出さない）。

    Args:
        name: 吹いたプレイヤーの呼び方。
        doused: 火を消した爆弾の数。
        washed: 流したうんこの数。
    """
    parts: list[str] = []
    if doused:
        parts.append(DOUSED.format(count=doused))
    if washed:
        parts.append(WASHED.format(count=washed))
    if not parts:
        return None
    return SPRAYED.format(name=name, what="・".join(parts))


def reason_text(reason: SuddenDeathReason) -> str:
    """延長戦に入ったわけの呼び方。"""
    match reason:
        case SuddenDeathReason.ALL_DOWN:
            return ALL_DOWN
        case SuddenDeathReason.TIME_UP:
            return TIME_UP
        case _:
            assert_never(reason)


def sudden_death(reason: SuddenDeathReason) -> str:
    """延長戦に入った通知。

    体力・爆弾・火力・靴・長さは、延長戦の決まり（`rules/tuning.py`）から作る。原型の
    文は上限の値を差し込んでいる（`BOMB_MAX` など）ので、値を変えれば文も変わる。体力は
    爆風何回ぶんかで書く（原型の HP は爆風1回で1減る）。
    """
    return SUDDEN_DEATH.format(
        reason=reason_text(reason),
        hp=hits_for_hp(SUDDEN_DEATH_HP),
        bombs=MAX_BOMBS,
        power=MAX_POWER,
        shoes=MAX_SHOES,
        seconds=ceil_seconds(SUDDEN_DEATH_LENGTH),
    )


def pad_unsupported(pad: str) -> str:
    """標準でないパッドをつないだ通知。`pad` はパッドの名前（原型の `gp.id`）。"""
    return PAD_UNSUPPORTED.format(pad=pad)


def cpu_took_over(name: str) -> str:
    """抜けたプレイヤーを CPU が引き継いだ通知。`name` は動物の名前。"""
    return CPU_TOOK_OVER.format(name=name)


def ceil_seconds(ticks: int) -> int:
    """tick を秒にする。端数は切り上げる。

    整数の割り算で切り上げる（小数にすると、割り切れる所で丸めの誤差が出うる）。
    """
    return -(-ticks // TICKS_PER_SECOND)
