"""横の板のキーの案内の中身の検査。

形と字は原型（`legacy/animal-bomber.html`）の `renderKeyHelp`（L5560-5616）。行を原型の
書き方（キーは `${K('W')}`、太字は `<b>…</b>`）に戻して、原型のファイルの中にそのまま
見つかるかも見る。
"""

import re
from functools import cache
from pathlib import Path

import pytest

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState
from animal_bomber.domain.systems.negibon import send_to_lane
from animal_bomber.presentation.hud.key_help import (
    HelpRow,
    KeyHelpSource,
    SpanKind,
    describe_key_help,
)
from animal_bomber.presentation.hud.roster import Cpu, Human, Roster, local_roster
from tests.helpers import make_world

LEGACY = Path(__file__).resolve().parents[3] / "legacy" / "animal-bomber.html"

NORMAL = CpuLevelKey.NORMAL
SOLO: Roster = local_roster(1, (NORMAL, NORMAL, NORMAL))
DUO: Roster = local_roster(2, (NORMAL, NORMAL))

SOLO_ROWS = [
    "そうさ",
    "うごく [W][A][S][D] / [↑][←][↓][→]",
    "ばくだん [Space][Enter][Z][/]",
    "とぶ [E][Q][X][C][R][Shift]（長押しでとくぎ🍗）",
]
"""1P のうさぎだけが人間のときの、操作の段（原型 L5586-5589）。"""

LANE_NOTE = (
    "生きてるヤツに当てると交代して復活（HP1・パワーアップは維持）。残り1分で退場"
)


def world_of(*animals: Animal) -> WorldState:
    return make_world(animals=animals)


def source(
    world: WorldState,
    roster: Roster,
    *,
    pad: bool = False,
    pad_in_match: bool = True,
    paused: bool = False,
    can_pause: bool = True,
) -> KeyHelpSource:
    return KeyHelpSource(
        world=world,
        roster=roster,
        pad_connected=pad,
        pad_in_match=pad_in_match,
        paused=paused,
        can_pause=can_pause,
    )


def texts(rows: tuple[HelpRow, ...]) -> list[str]:
    return ["---" if row.rule else row.text for row in rows]


def legacy_form(row: HelpRow) -> str:
    """行を原型の書き方に戻す（キーは `${K('W')}`、太字は `<b>…</b>`）。"""
    out = []
    for span in row.spans:
        match span.kind:
            case SpanKind.KEY:
                out.append(f"${{K('{span.text}')}}")
            case SpanKind.BOLD:
                out.append(f"<b>{span.text}</b>")
            case SpanKind.TEXT:
                out.append(span.text)
    return "".join(out)


@cache
def legacy_text() -> str:
    """原型のファイル。`+` で行をまたいでつないだ文字列は、つないだ形に戻す。"""
    text = LEGACY.read_text(encoding="utf-8")
    return re.sub(r"`\s*\+\s*`", "", text)


class Test操作の段:
    def test_人間が1なら_そうさの形で_技の見出しはその動物の技(self) -> None:
        world = world_of(Animal.RABBIT, Animal.FOX, Animal.MOLE, Animal.FROG)
        rows = describe_key_help(source(world, SOLO))
        assert texts(rows) == [*SOLO_ROWS, "[P] ポーズ"]
        assert rows[0].spans[0].kind is SpanKind.BOLD

    def test_人間が2なら_1Pと2Pの形で_それぞれのキーだけを出す(self) -> None:
        world = world_of(Animal.RABBIT, Animal.FROG, Animal.FOX, Animal.MOLE)
        rows = describe_key_help(source(world, DUO))
        assert texts(rows) == [
            "1P 🐰",
            "[W][A][S][D] ／ ばくだん [Space][Z]",
            "とぶ [E][Q][X][C][R][左Shift]（長押しでとくぎ🍗）",
            "2P 🐸",
            "[↑][←][↓][→] ／ ばくだん [Enter][/]",
            "した [右Shift][.][,][M][N]（長押しでとくぎ🍗）",
            "[P] ポーズ",
        ]
        assert rows[3].margin_top == 7

    @pytest.mark.parametrize(
        ("animal", "label"),
        [
            (Animal.RABBIT, "とぶ"),
            (Animal.FROG, "した"),
            (Animal.FOX, "ドン置き"),
            (Animal.ELEPHANT, "はなみず"),
            (Animal.MOLE, "とくぎ🍗"),
        ],
    )
    def test_技の見出しは動物ごと(self, animal: Animal, label: str) -> None:
        world = world_of(animal, Animal.FOX)
        rows = describe_key_help(source(world, local_roster(1, (NORMAL,))))
        assert rows[3].text.startswith(f"{label} [E]")

    def test_CPUのプレイヤーは数えない(self) -> None:
        """CPU だけの試合は原型の2人の形で、見出しの絵文字は空・技は「技」。"""
        world = world_of(Animal.RABBIT, Animal.FROG)
        roster: Roster = (Cpu(1, NORMAL), Cpu(2, NORMAL))
        assert texts(describe_key_help(source(world, roster)))[:3] == [
            "1P ",
            "[W][A][S][D] ／ ばくだん [Space][Z]",
            "技 [E][Q][X][C][R][左Shift]（長押しでとくぎ🍗）",
        ]


class Testパッドとポーズの行:
    def test_パッドを認識していて_パッドを試合に繋ぐ遊び方なら_パッドの段(self) -> None:
        world = world_of(Animal.FROG, Animal.FOX)
        rows = describe_key_help(source(world, local_roster(1, (NORMAL,)), pad=True))
        assert texts(rows)[4:] == [
            "🎮 [十字][スティック] うごく ／ ばくだん [A][R1]",
            "した [B][X][Y][L1]（長押しでとくぎ🍗）",
            "[P][Start] ポーズ",
        ]

    def test_パッドが無ければ_パッドの段もStartも出さない(self) -> None:
        world = world_of(Animal.FROG, Animal.FOX)
        rows = texts(describe_key_help(source(world, local_roster(1, (NORMAL,)))))
        assert not any("🎮" in row or "Start" in row for row in rows)

    def test_2人の遊び方では_パッドを認識していてもパッドの段を出さない(self) -> None:
        """2人の遊び方はパッドを試合に繋がない（原型 L3570・L5602）。Start は出す。"""
        world = world_of(Animal.RABBIT, Animal.FROG)
        rows = texts(
            describe_key_help(source(world, DUO, pad=True, pad_in_match=False))
        )
        assert not any("🎮" in row for row in rows)
        assert rows[-1] == "[P][Start] ポーズ"
        assert not any("Select" in row for row in rows)

    def test_Selectの行は_ポーズ中だけ(self) -> None:
        world = world_of(Animal.RABBIT, Animal.FROG)
        roster = local_roster(1, (NORMAL,))
        playing = texts(describe_key_help(source(world, roster, pad=True)))
        paused = texts(describe_key_help(source(world, roster, pad=True, paused=True)))
        assert not any("Select" in row for row in playing)
        assert paused[-1] == "[Select] 設定へもどる"
        assert paused[:-1] == playing

    def test_ポーズできない端末は_ポーズの行を出さず_Selectの行をいつも出す(
        self,
    ) -> None:
        """Select の条件は原型のゲストと同じ。ポーズの行は、通信対戦では出さない。"""
        world = world_of(Animal.RABBIT, Animal.FROG)
        roster: Roster = (Human("1P", local=True), Human("2P"))
        rows = texts(
            describe_key_help(source(world, roster, pad=True, can_pause=False))
        )
        assert not any("ポーズ" in row for row in rows)
        assert rows[-1] == "[Select] 設定へもどる"
        no_pad = texts(describe_key_help(source(world, roster, can_pause=False)))
        assert not any("Select" in row or "ポーズ" in row for row in no_pad)


class Test葱ボンの段:
    def test_外周にいる人間には_いちばん上に移動と発射のキーと注記を出す(self) -> None:
        world = world_of(Animal.RABBIT, Animal.FOX)
        send_to_lane(world, world.players[0])
        rows = describe_key_help(source(world, local_roster(1, (NORMAL,))))
        assert texts(rows)[:5] == [
            "🌿 うさぎ は葱ボン＝場外",
            "外周を移動 [W][A][S][D] / [↑][←][↓][→]",
            "葱を発射 [Space] か [Enter]",
            LANE_NOTE,
            "---",
        ]
        assert texts(rows)[5:9] == SOLO_ROWS
        note = rows[3]
        assert [span.kind for span in note.spans] == [
            SpanKind.TEXT,
            SpanKind.BOLD,
            SpanKind.TEXT,
        ]
        assert note.spans[1].text == "交代して復活"

    @pytest.mark.parametrize(
        ("player", "heading", "move", "fire"),
        [
            (
                0,
                "🌿 うさぎ（1P） は葱ボン＝場外",
                "外周を移動 [W][A][S][D]",
                "葱を発射 [Space] か [Z]",
            ),
            (
                1,
                "🌿 かえる（2P） は葱ボン＝場外",
                "外周を移動 [↑][←][↓][→]",
                "葱を発射 [Enter] か [/]",
            ),
        ],
    )
    def test_2人のときは_札を添えて_それぞれのキーだけ(
        self, player: PlayerId, heading: str, move: str, fire: str
    ) -> None:
        world = world_of(Animal.RABBIT, Animal.FROG)
        send_to_lane(world, world.players[player])
        rows = texts(describe_key_help(source(world, DUO)))
        assert rows[:3] == [heading, move, fire]
        assert rows[5] == "1P 🐰"

    def test_外周にいるCPUには出さない(self) -> None:
        world = world_of(Animal.RABBIT, Animal.FOX)
        send_to_lane(world, world.players[1])
        rows = texts(describe_key_help(source(world, local_roster(1, (NORMAL,)))))
        assert rows[0] == "そうさ"
        assert not any("葱ボン" in row for row in rows)


class Test通信対戦:
    def test_この端末のプレイヤーだけを_1人の形で出す(self) -> None:
        """原型は人間の数で2人の形にする。この版は、この端末のプレイヤーだけ。"""
        world = world_of(Animal.RABBIT, Animal.FROG, Animal.FOX, Animal.ELEPHANT)
        roster: Roster = (
            Human("1P"),
            Human("2P", local=True),
            Cpu(1, NORMAL),
            Human("4P"),
        )
        send_to_lane(world, world.players[0])
        send_to_lane(world, world.players[1])
        rows = texts(
            describe_key_help(source(world, roster, pad=True, can_pause=False))
        )
        assert rows[0] == "🌿 かえる は葱ボン＝場外"
        assert not any("うさぎ" in row for row in rows)
        assert "そうさ" in rows
        assert "した [E][Q][X][C][R][Shift]（長押しでとくぎ🍗）" in rows
        assert "した [B][X][Y][L1]（長押しでとくぎ🍗）" in rows
        assert not any(row.startswith("1P") or row.startswith("2P") for row in rows)


class Test原型の文:
    def test_決まった行は_原型の書き方のまま原型にある(self) -> None:
        world = world_of(Animal.RABBIT, Animal.FROG)
        send_to_lane(world, world.players[0])
        solo = describe_key_help(
            source(world, local_roster(1, (NORMAL,)), pad=True, paused=True)
        )
        duo = describe_key_help(source(world, DUO))
        # 外周の移動と発射は、原型ではキーの並びを別に組んで差し込む（L5572-5579）。
        move, fire = solo[1], solo[2]
        assert '<div class="r">外周を移動 ${mv}</div>' in legacy_text()
        assert '<div class="r">葱を発射 ${fire}</div>' in legacy_text()
        assert legacy_form(HelpRow(move.spans[1:])) in legacy_text()
        assert legacy_form(HelpRow(fire.spans[1:])) in legacy_text()
        fixed = [
            solo[3],  # 注記
            solo[5],  # そうさ
            solo[6],  # うごく
            solo[7],  # ばくだん
            solo[9],  # パッドの段の1行目
            solo[-1],  # Select
            *[row for row in duo if "／ ばくだん" in row.text],
        ]
        text = legacy_text()
        for row in fixed:
            assert legacy_form(row) in text, row.text
        # 技の行は、頭の見出しを除いた残り（キーと末尾）。
        for row in (*solo, *duo):
            if row.text.endswith("（長押しでとくぎ🍗）"):
                assert legacy_form(HelpRow(row.spans[1:])) in text, row.text
        assert "${K('P')}${PAD.on?K('Start'):''} ポーズ" in text
