"""横の板の時計と名札の中身（原型の `renderCards` L5497-5548）。

文と値を返すだけで、描かない。どこにどう並べるか（字の大きさ・色・札の枠）は描く側が
決める。ルールの層の状態は読むだけにする（書き換えると、画面を出したときだけ試合が
変わる）。

原型は名札を約 4 Hz で丸ごと作り直す（`update` の `G.elapsed%0.25<dt`。L4406）。
落とし穴の残り秒（小数1桁）もその粒で変わって見える。作り直す間隔は描く側が決め、
ここの関数は渡された盤面の値をそのまま文にする。原型が 4 Hz を待たずにすぐ作り直す
イベント（被弾など）は、名札の決まりとしてここに置く（`refreshes_panel`）。
"""

import math
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from typing import Final, assert_never

from animal_bomber.domain.abilities.frog import TONGUE_REACH
from animal_bomber.domain.core.tick import TICKS_PER_SECOND
from animal_bomber.domain.events import (
    BurntOff,
    EffectApplied,
    LanesClosed,
    Moment,
    PlayerDown,
    PlayerHurt,
    ReachRestored,
    Revived,
    RoundEnded,
    SimEvent,
    SuddenDeath,
    TechniqueMoment,
    TechniqueUsed,
)
from animal_bomber.domain.rules.animals import stats_of
from animal_bomber.domain.rules.items import POOP_EFFECTS
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import STARTING_HP, SUDDEN_DEATH_HP
from animal_bomber.domain.state.actions import Dig, Tongue
from animal_bomber.domain.state.actors import BurntTongue, Pit
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.player import (
    Alive,
    Negibon,
    Out,
    PlayerState,
    power_of,
)
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.animal_text import (
    animal_emoji,
    animal_name,
    special_emoji,
    special_name,
)
from animal_bomber.presentation.audio.countdown import seconds_left
from animal_bomber.presentation.emoji import HOLE, PICK, POOP_MARKS
from animal_bomber.presentation.hud.roster import Roster, is_cpu, tag_of
from animal_bomber.presentation.menu.choices import format_seconds

WARN_SECONDS: Final = 30
"""残り時間がこれ以下（秒）になったら時計を目立たせる（原型 L5547 の `t<=30`）。"""

CLOCK_CAPTION: Final = "TIME"
"""時計の下の行（原型 L520）。延長戦に入っても変えない（原型も変えない）。"""

OUT_CONDITION: Final = "💀 退場"
"""退場したプレイヤーの体力の行（原型 L5503）。"""

NEGIBON_CONDITION: Final = "🌿 葱ボン（場外）"
"""外周にいるプレイヤーの体力の行（原型 L5504）。"""

NEGIBON_TAG: Final = "葱ボン"
"""外周にいるプレイヤーの名札に足す札（原型 L5509）。"""

FULL_HEART: Final = "\N{HEAVY BLACK HEART}\N{VARIATION SELECTOR-16}"
"""残っている体力のハート（原型 `heartsOf` の ❤️。見え方を選ぶ印 U+FE0F まで同じ）。"""

HALF_HEART: Final = "💔"
"""半分だけ残っているハート（原型 `heartsOf`）。

体当たりで進む最中に受ける、半分の傷で出る。
"""

LOST_HEART: Final = "🖤"
"""減ったぶんのハート（原型 `heartsOf`）。"""

PANEL_MOMENTS: Final = frozenset({Moment.PIT_DUG})
"""横の板をすぐ作り直す、技の途中のこと（穴を掘り終えた。原型 L2578）。"""


@dataclass(frozen=True, slots=True)
class HudSource:
    """横の板と幕を作るのに要るもの。盤面だけでは足りない（勝ち数・設定・誰が操作しているか）。"""

    world: WorldState
    match: MatchState
    config: MatchConfig
    roster: Roster
    between_rounds: bool
    """ラウンドが決まり、次の盤面を待っている最中か（`GameSession.between_rounds`）。"""


@dataclass(frozen=True, slots=True)
class ClockView:
    """時計の中身（原型 L517-521 と L5542-5547）。"""

    round: int
    """出すラウンドの番号。"""
    wins_to_take: int
    time: str
    """残り時間（「2:59」）。"""
    warn: bool
    """残りが `WARN_SECONDS` 以下か（原型の `.warn`。数字を赤くして明滅させる）。"""

    @property
    def heading(self) -> str:
        """上の行（「ROUND 1　3勝先取」。間は全角の空白。原型 L5546）。"""
        return f"ROUND {self.round}\N{IDEOGRAPHIC SPACE}{self.wins_to_take}勝先取"


def remaining_seconds(world: WorldState) -> int:
    """残り時間（秒）。端数は切り上げ、0 より下にしない。

    原型の `max(0, ceil(G.time))`。延長戦に入ると、時間切れの時刻が置き直される
    （`WorldState.ends_at`）ので、延長戦の長さから数え直す（原型も `G.time=60` から
    数え直す）。
    """
    return max(0, seconds_left(world.now, world.ends_at))


def describe_clock(source: HudSource) -> ClockView:
    """時計の中身。

    ⚠️ ラウンドが決まった tick に、試合の側（`systems/round.py` の `apply_outcome`）は
    ラウンドの番号を次へ進めている。決着のあとの待ちの間の盤面は決まったラウンドのもの
    なので、番号も1つ前を出す（原型は幕を出している間も、決まったラウンドの番号の
    まま。番号を進めるのは次のラウンドを始めるとき）。試合が決まったときは番号を進めない
    ので、そのまま出す。
    """
    left = remaining_seconds(source.world)
    number = source.match.round - 1 if source.between_rounds else source.match.round
    return ClockView(
        round=number,
        wins_to_take=source.config.wins_to_take,
        time=format_seconds(left),
        warn=left <= WARN_SECONDS,
    )


def hearts(hp: int, max_hp: int) -> str:
    """体力をハートで表す（原型 `heartsOf` L5490-5495）。

    この版の体力は半分の単位の整数（爆風1回で 2 減る）なので、2 でハート1つ。原型の
    体力は 0.5 刻みの小数で、整数部ぶんの ❤️、端数が 0.25 以上なら 💔、最大から減った
    ぶんの 🖤（`Math.round`）を並べる。同じ結果になる式に書き換えてある（体力のすべての
    値で原型の式と並べるテストがある）。減ったぶんは黒いハートで残す。あといくつで
    倒れるかが一目で分かる。

    Args:
        hp: いまの体力（半分の単位）。
        max_hp: そのラウンドの始まりの体力（半分の単位。`max_hp_of`）。
    """
    full = hp // 2
    half = hp % 2
    lost = max(0, (max_hp + 1) // 2 - full - half)
    return FULL_HEART * full + HALF_HEART * half + LOST_HEART * lost


def max_hp_of(source: HudSource, player: PlayerState) -> int:
    """そのプレイヤーの、いまの体力の上限（半分の単位。原型の `maxHp`）。

    ラウンドの始まりの体力（設定の値に動物ごとの上乗せを足したもの。原型の `makePlayer`
    L1187）。延長戦に入ると、加わったプレイヤーの上限は延長戦の体力になる（原型の
    `enterSuddenDeath` L4455 の `p.maxHp=1`）。
    """
    if source.world.sudden_death:
        return SUDDEN_DEATH_HP
    starting = source.config.starting_hp
    base = STARTING_HP if starting is None else starting[player.id]
    return base + stats_of(player.animal).hp_bonus


class CardLook(Enum):
    """名札の見た目の種類（原型の `.pcard` に足す名前。L5502）。"""

    PLAYING = "playing"
    """盤面にいる（ふつうの札）。"""
    OUT = "out"
    """退場した（原型の `.pcard.dead`。薄く、白黒にする。L86）。"""
    NEGIBON = "negibon"
    """外周にいる（原型の `.pcard.negi`。緑の枠と内側の光。L87）。"""


class TagStyle(Enum):
    """名札の札の色の種類（原型の `.tag`。L5506-5509）。"""

    HUMAN = "human"
    """人間（原型の `.tag`）。"""
    CPU = "cpu"
    """CPU（原型の `.tag.cpu`）。"""
    NEGIBON = "negibon"
    """外周にいる（原型の `.tag.negi`）。"""


@dataclass(frozen=True, slots=True)
class CardTag:
    """名札の1行目で、動物の名前の横に並べる札1つ。"""

    text: str
    style: TagStyle


@dataclass(frozen=True, slots=True)
class PlayerCard:
    """プレイヤー1人ぶんの名札（原型 L5530-5538 の並び）。"""

    emoji: str
    """左に大きく出す動物の絵文字。"""
    name: str
    """動物の名前（1行目）。"""
    tags: tuple[CardTag, ...]
    """名前の横の札（「1P」か「CPU1・ふつう」と、外周にいる間は「葱ボン」）。"""
    stars: str
    """取った勝ち星と、優勝までの残り（「★☆☆」）。"""
    condition: str
    """体力のハート、または盤面にいないわけ。"""
    stats: tuple[str, str, str]
    """爆弾・火力・靴（「💣1」「🔥2」「👟0」）。"""
    effects: tuple[str, ...]
    """かかっている状態と、使えるとくぎ（原型の `.fx`。空白でつないで1行に出す）。"""
    look: CardLook

    @property
    def effects_line(self) -> str:
        """状態の行（原型の `fx.join(' ')`）。"""
        return " ".join(self.effects)


def describe_players(source: HudSource) -> tuple[PlayerCard, ...]:
    """全員ぶんの名札。プレイヤー番号の順（原型の `players` の順）。"""
    return tuple(describe_player(source, player) for player in source.world.players)


def describe_player(source: HudSource, player: PlayerState) -> PlayerCard:
    """プレイヤー1人ぶんの名札。"""
    world, roster = source.world, source.roster
    wins = source.match.wins_of(player.id)
    left = max(0, source.config.wins_to_take - wins)
    style = TagStyle.CPU if is_cpu(roster, player.id) else TagStyle.HUMAN
    tags = [CardTag(tag_of(roster, player.id), style)]
    life = player.life
    match life:
        case Alive():
            look = CardLook.PLAYING
            condition = hearts(player.hp, max_hp_of(source, player))
        case Negibon():
            look = CardLook.NEGIBON
            condition = NEGIBON_CONDITION
            tags.append(CardTag(NEGIBON_TAG, TagStyle.NEGIBON))
        case Out():
            look = CardLook.OUT
            condition = OUT_CONDITION
        case _:
            assert_never(life)
    return PlayerCard(
        emoji=animal_emoji(player.animal),
        name=animal_name(player.animal),
        tags=tuple(tags),
        stars="★" * wins + "☆" * left,
        condition=condition,
        stats=(
            f"💣{player.max_bombs}",
            f"🔥{power_of(player)}",
            f"👟{player.shoes}",
        ),
        effects=card_effects(world, player),
        look=look,
    )


def card_effects(world: WorldState, player: PlayerState) -> tuple[str, ...]:
    """状態の行に並べるもの。並びと字は原型 L5511-5527 と同じ。

    原型は、プレイヤーの状態（盤面・外周・退場）を見ずに組む。退場したプレイヤーにも、
    残っているとくぎと状態を出す（倒れて退場したときは、かかっていた状態もとくぎも
    消えない。原型の `kill`、この版の `systems/damage.py` の `hurt`）。外周へ回った
    ときは状態ととくぎの印が消えるので、何も出ない（原型の `toNegibon`）。

    とくぎは、持っている印（`has_special`）で見る（原型の `p.chicken`）。外周から戻った
    プレイヤーは、回数だけが残って印が外れていることがあり、そのとくぎは出せないので出さ
    ない。「×n」は回数が2以上のとき（原型 L5513）。
    """
    effects = player.effects
    out: list[str] = []
    if player.has_special:
        times = player.special_charges or 1
        suffix = f"×{times}" if times > 1 else ""
        out.append(
            f"{special_emoji(player.animal)}{special_name(player.animal)}{suffix}"
        )
    if effects.has(EffectKind.SCATTERING):
        out.append("💩ポロポロ中")
    if isinstance(player.action, Tongue):
        out.append("👅舌")
    scar = _burnt_tongue_of(world, player)
    if scar is not None:
        seconds = -(-scar.until_regen // TICKS_PER_SECOND)
        out.append(f"👅🔥舌 {scar.limit}/{TONGUE_REACH}マス（{seconds}秒で+1）")
    if isinstance(player.action, Dig):
        out.append(f"{PICK}穴をほってる")
    if effects.has(EffectKind.PITFALL):
        out.append(
            f"{HOLE}落とし穴 {fixed_seconds(effects.remaining(EffectKind.PITFALL))}秒"
        )
    # 穴は盤面に描かないので、しかけた数をここで見せる（原型の注記 L5520）。
    pits = _count_pits(world, player)
    if pits:
        out.append(f"{HOLE}しかけた穴 {pits}個")
    if effects.has(EffectKind.STUN):
        out.append("😭涙")
    if effects.has(EffectKind.SLIDE):
        out.append("🍌すべり")
    labels = {poop.kind: poop.label for poop in POOP_EFFECTS}
    for kind, mark in POOP_MARKS:
        if effects.has(kind):
            out.append(f"{mark}{labels[kind]}")
    return tuple(out)


def fixed_seconds(ticks: int) -> str:
    """tick を秒にして、小数1桁の文にする（原型の `toFixed(1)` と同じ丸め）。

    原型は秒の小数（浮動小数）を `toFixed(1)` で書く。`toFixed` は、浮動小数の正確な値に
    いちばん近い小数1桁を選び、ちょうど真ん中なら大きいほうを選ぶ。Python の `round` と
    書式（`:.1f`）は真ん中で偶数のほうを選ぶので、0.25 秒が「0.2」になる（原型は
    「0.3」）。ここでは秒の浮動小数の正確な値を分数で持ち、真ん中なら大きいほうへ
    丸める。
    """
    exact = Fraction(ticks / TICKS_PER_SECOND)
    tenths = math.floor(exact * 10 + Fraction(1, 2))
    return f"{tenths // 10}.{tenths % 10}"


def refreshes_panel(event: SimEvent) -> bool:
    """横の板をすぐ作り直すイベントか（ふだんは約 4 Hz。`render/panel/side_panel.py`）。

    原型が `renderCards` を、4 Hz を待たずに呼ぶ場面：被弾（L1668）・外周へ回った・
    入れ替わった（L2270・L2355）・外周が閉じた（L2362）・舌が焼き切れた（L2489）・
    穴を掘り終えた・落とし穴にはまった（L2578・L2598）・とくぎを使った（L2627）・
    舌が戻った（L4308）・延長戦（L4464）・決着（L4510）。ラウンドの始まり（L4158）は、
    呼ぶ側（`app/shell.py`）が別に見る。ポーズの切り替えとゲーム速度では、原型は
    `renderCards` を呼ばない（キーの案内とつまみだけを替える。L4217-4221・
    L6049-6052。`render/panel/side_panel.py` の `PanelPart`）。
    """
    match event:
        case (
            PlayerHurt()
            | PlayerDown()
            | Revived()
            | LanesClosed()
            | BurntOff()
            | ReachRestored()
            | SuddenDeath()
            | RoundEnded()
        ):
            return True
        case TechniqueUsed(special=special):
            return special
        case TechniqueMoment(moment=moment):
            return moment in PANEL_MOMENTS
        case EffectApplied(effect=effect):
            return effect is EffectKind.PITFALL
        case _:
            # ほかのイベントは名札の中身を約 4 Hz の作り直しで出す（原型と同じ）。
            return False


def _burnt_tongue_of(world: WorldState, player: PlayerState) -> BurntTongue | None:
    """そのプレイヤーの焼けた舌。焼けていない（伸ばせる長さが元のまま）なら None。

    原型の条件 `p.animal.tongue && tongueReach(p)<TONGUE_MAX`（L5516）と同じ。焼けた
    舌は元の長さまで戻ったら盤面から消える（`abilities/frog.py` の
    `advance_burnt_tongue`）。
    """
    for actor in world.actors:
        if isinstance(actor, BurntTongue) and actor.owner == player.id:
            return actor
    return None


def _count_pits(world: WorldState, player: PlayerState) -> int:
    """そのプレイヤーがしかけた穴の数（原型 L5522）。"""
    count = 0
    for actor in world.actors:
        if isinstance(actor, Pit) and actor.owner == player.id:
            count += 1
    return count
