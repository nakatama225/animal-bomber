"""状態の印の並びと、画面の揺れのしきいの検査。

原型の命令の列（`test_legacy_art.py`）には、印が1つか3つ並ぶ場面と、揺れが 0 と 6 の
場面しか無い。印の1つずつの条件と並び、揺れのしきい（0.2px）の前後は、ここで見る。
"""

import pytest

from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.presentation.animal_text import special_emoji
from animal_bomber.presentation.cosmetic_rng import CosmeticRng, ScriptedRandom
from animal_bomber.presentation.emoji import HOLE, PICK
from animal_bomber.presentation.render.art.frame import shake_offset
from animal_bomber.presentation.render.art.player_marks import status_marks


def marks_of(effects: tuple[EffectKind, ...] = (), **flags: bool) -> list[str]:
    defaults = {
        "special": False,
        "pitfall": False,
        "digging": False,
        "tongue": False,
        "scattering": False,
    }
    return status_marks(Animal.FOX, effects=effects, **{**defaults, **flags})


class Test印:
    @pytest.mark.parametrize(
        ("effects", "flags", "mark"),
        [
            ((EffectKind.STUN,), {}, "😭"),
            ((EffectKind.SLIDE,), {}, "🍌"),
            ((), {"pitfall": True}, HOLE),
            ((), {"digging": True}, PICK),
            ((), {"tongue": True}, "👅"),
            ((), {"scattering": True}, "💩"),
            ((), {"special": True}, "🔵"),
            ((EffectKind.SLOW,), {}, "🐌"),
        ],
    )
    def test_1つだけかかっていれば_その印だけ(
        self,
        effects: tuple[EffectKind, ...],
        flags: dict[str, bool],
        mark: str,
    ) -> None:
        assert marks_of(effects, **flags) == [mark]

    def test_全部かかっていれば_原型の並び(self) -> None:
        """チキン・泣き・穴・掘る・バナナ・舌・撒く・うんこの効果（POOPS の順）。"""
        effects = tuple(EffectKind)
        everything = marks_of(
            effects,
            special=True,
            pitfall=True,
            digging=True,
            tongue=True,
            scattering=True,
        )
        assert everything == [
            special_emoji(Animal.FOX),
            "😭",
            HOLE,
            PICK,
            "🍌",
            "👅",
            "💩",
            "🔄",
            "🚫",
            "💨",
            "🕯️",
            "🎰",
            "🐌",
        ]


class Test画面の揺れ:
    def test_しきい以下なら揺らさず_乱数も引かない(self) -> None:
        source = ScriptedRandom([])
        assert shake_offset(0.2, CosmeticRng(source)) is None
        assert shake_offset(0.1, CosmeticRng(source)) is None
        assert source.used == []

    def test_しきいを超えたら_横と縦の順に乱数を2つ引く(self) -> None:
        source = ScriptedRandom([0.75, 0.25])
        assert shake_offset(0.4, CosmeticRng(source)) == (0.1, -0.1)
        assert source.used == [0.75, 0.25]
