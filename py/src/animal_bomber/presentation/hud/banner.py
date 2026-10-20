"""ラウンドの幕と優勝の幕の中身（原型の `endGame` L4467-4511）。

文と値を返すだけで、描かない。幕は決着の tick にすぐ出る（原型も待ちや演出を挟まない）。
文の形は原型の3つ（優勝・ラウンドの勝ち・ひきわけ）を逐語で写した。

- 優勝：題は「うさぎ（1P） 優勝！」（CPU は「（CPU）」）。延長戦で決まっても、そう
  添えない
- ラウンドの勝ち：題は動物の名前だけ（「ラウンド1　うさぎの かち」）。同じ動物を2人が
  選ぶと、題からはどちらの勝ちか分からない（原型 L4494 のまま）。延長戦で決まったら
  「⚡サドンデス決着」を添える
- ひきわけ：わけ（「同時にやられた」「時間切れ」）と、時間切れなら残ったプレイヤー

勝ち数の行は、全員の「絵文字と勝ち数」を全角の空白でつなぐ（原型 L4482）。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from animal_bomber.domain.events import MatchEnded, RoundEnded, SimEvent
from animal_bomber.domain.state.player import PlayerId, is_alive
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.animal_text import animal_emoji, animal_name
from animal_bomber.presentation.hud.roster import is_cpu, label_of
from animal_bomber.presentation.hud.scoreboard import HudSource
from animal_bomber.presentation.notices import ALL_DOWN, TIME_UP

CHAMPION_EMOJI: Final = "🏆"
"""優勝の幕の絵文字（原型 L4485）。"""

DRAW_EMOJI: Final = "🤝"
"""ひきわけの幕の絵文字（原型 L4501）。"""

NEXT_ROUND_BUTTON: Final = "つぎのラウンド ▶"
"""ラウンドの幕のボタン（原型 L4498）。"""

AGAIN_BUTTON: Final = "もういっかい"
"""優勝の幕のボタン（原型 L4489）。"""

SETUP_BUTTON: Final = "⚙ 設定をやりなおす"
"""どちらの幕にも出す2つ目のボタン（原型 L549）。

行き先はタイトル（原型の `backToSetup`）。
"""

SUDDEN_NOTE: Final = "⚡サドンデス決着"
"""延長戦で決まったラウンドの幕に添える行（原型 L4497）。"""

BOARD_SEPARATOR: Final = "\N{IDEOGRAPHIC SPACE}"
"""勝ち数の行の区切り（全角の空白。原型 L4482）。"""

LEFT_LABEL: Final = "\N{IDEOGRAPHIC SPACE}のこり: "
"""時間切れのひきわけで、残ったプレイヤーの前に置く文（原型 L4504）。"""


@dataclass(frozen=True, slots=True)
class BannerView:
    """幕の中身（原型の `#bE`・`#bT`・`#bS`・`#bAgain`）。"""

    emoji: str
    """大きく出す絵文字。"""
    title: str
    """題。"""
    summary: str
    """題の下の1行目（勝ち数の残り・達成・ひきわけのわけ）。"""
    board: str
    """勝ち数の行（原型は1行目より大きい字で出す）。"""
    note: str | None
    """勝ち数の行の下に添える行（延長戦で決まったラウンド）。無ければ None。"""
    button: str
    """1つ目のボタンの文（「つぎのラウンド ▶」か「もういっかい」）。"""
    final: bool
    """試合が決まった幕か。"""


def describe_banner(
    source: HudSource, ended: RoundEnded, champion: PlayerId | None
) -> BannerView:
    """決着の tick の幕。

    決着の tick のうちに、決まったラウンドの盤面と、勝ち数を足したあとの試合の状態で
    呼ぶ（試合を進める側は、決着のあとの待ちの間は盤面を差し替えない。`GameSession`）。

    Args:
        source: 決着の tick を進めたあとの横の板の材料。
        ended: 決まったラウンド。
        champion: 試合を取ったプレイヤー。試合が決まっていなければ None。
    """
    world, match, roster = source.world, source.match, source.roster
    wins = source.config.wins_to_take
    board = BOARD_SEPARATOR.join(
        f"{animal_emoji(player.animal)}{match.wins_of(player.id)}"
        for player in world.players
    )
    if champion is not None:
        animal = world.players[champion].animal
        who = (
            "（CPU）"
            if is_cpu(roster, champion)
            else f"（{label_of(roster, champion, animal)}）"
        )
        return BannerView(
            emoji=CHAMPION_EMOJI,
            title=f"{animal_name(animal)}{who} 優勝！",
            summary=f"{wins}勝先取を達成（全{ended.round}ラウンド）",
            board=board,
            note=None,
            button=AGAIN_BUTTON,
            final=True,
        )
    head = f"ラウンド{ended.round}{BOARD_SEPARATOR}"
    winner = ended.winner
    if winner is not None:
        animal = world.players[winner].animal
        return BannerView(
            emoji=animal_emoji(animal),
            title=f"{head}{animal_name(animal)}の かち",
            summary=f"{wins}勝先取まで あと {wins - match.wins_of(winner)}勝",
            board=board,
            note=SUDDEN_NOTE if world.sudden_death else None,
            button=NEXT_ROUND_BUTTON,
            final=False,
        )
    return BannerView(
        emoji=DRAW_EMOJI,
        title=f"{head}ひきわけ",
        summary=draw_reason(world),
        board=board,
        note=None,
        button=NEXT_ROUND_BUTTON,
        final=False,
    )


def draw_reason(world: WorldState) -> str:
    """ひきわけのわけ（原型 L4503-4504）。

    `RoundEnded` はわけを運ばないが、決まったラウンドの盤面から分かる。盤面にだれも
    いなければ「同時にやられた」、2人以上残っていれば時間切れで、残ったプレイヤーの
    動物の名前を「・」でつないで添える（`systems/round.py` の `judge_round` が引き分けに
    するのは、この2つだけ）。
    """
    left = [animal_name(player.animal) for player in world.players if is_alive(player)]
    if not left:
        return ALL_DOWN
    return f"{TIME_UP}{LEFT_LABEL}{'・'.join(left)}"


class RoundBanner:
    """いま出している幕。決着で出し、次のラウンドの盤面に替わったら消す。

    試合が決まった幕は、別の盤面を渡されても消さない（「もういっかい」を押すまで結果を
    見せる）。次の試合では作り直す。
    """

    def __init__(self) -> None:
        self._view: BannerView | None = None
        self._world: WorldState | None = None

    def observe(self, events: Sequence[SimEvent], source: HudSource) -> None:
        """1 tick ぶんのイベントを、その tick を進めたあとの材料と一緒に受け取る。

        ラウンドと試合が同じ tick に決まったら、試合が決まった幕を出す（原型の
        `endGame` も、優勝者がいれば優勝の幕を出す）。
        """
        ended: RoundEnded | None = None
        champion: PlayerId | None = None
        for event in events:
            match event:
                case RoundEnded():
                    ended = event
                case MatchEnded(champion=winner):
                    champion = winner
                case _:
                    # 幕を出すのは決着だけ（種類で振り分ける所ではないので、ほかは
                    # 見ない）。
                    pass
        if ended is None:
            return
        self._view = describe_banner(source, ended, champion)
        self._world = source.world

    def current(self, world: WorldState) -> BannerView | None:
        """いま出す幕。`world` は描く盤面。

        盤面が替わっていれば消す（試合が決まった幕は残す）。
        """
        view = self._view
        if view is None:
            return None
        if view.final or world is self._world:
            return view
        self._view = None
        return None
