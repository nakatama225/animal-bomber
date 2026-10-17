"""効果音の表。原型（`legacy/animal-bomber.html` の `SE`）の数値と式をそのまま写した。

効果音1つを、原型が作る順に並べた部品（`parts.py` の `Tone` と `Noise`）の列にする。
ここには原型が初めから持っていた音を置き、あとから足した音（アイテム・葱ボン・技・
延長戦）は `added_recipes.py` に分けてある（原型の `SE` も、その2つに分けて書いて
ある）。

⚠️ 数値は原型の式のまま書いてある（`523.25 * 2 ** (s / 12)` など）。半音の数の表に
書き換えないこと。原型を読み込んで書き出した固定値
（`tests/presentation/legacy_sound_values.json`）と突き合わせて確かめていて、式を
変えると、どこで原型から離れたのかを追えなくなる。
"""

from typing import assert_never

from animal_bomber.presentation.audio.added_recipes import added_recipe
from animal_bomber.presentation.audio.parts import (
    FilterKind,
    Noise,
    Part,
    Tone,
    Wave,
    band_noise,
)
from animal_bomber.presentation.audio.sounds import SoundName


def recipe(name: SoundName, intensity: int = 1) -> tuple[Part, ...]:
    """効果音1つの部品を、原型が作る順に返す。

    音を足すと、この `match` が型検査（mypy）で失敗する。分けた先の関数は、受け持つ
    名前のほかが来たら例外にする。

    Args:
        name: 効果音。
        intensity: 爆発の連鎖数（原型の `SE.explode(n)`）。ほかの音は見ない。
    """
    match name:
        case (
            SoundName.PLACE
            | SoundName.EXPLODE
            | SoundName.BREAK_BLOCK
            | SoundName.ITEM
            | SoundName.HURT
            | SoundName.DIE
            | SoundName.JUMP
            | SoundName.SPECIAL
            | SoundName.TICK
            | SoundName.UI
        ):
            return _play(name, intensity)
        case SoundName.WIN | SoundName.CHAMPION | SoundName.DRAW:
            return _round_end(name)
        case (
            SoundName.SLIP
            | SoundName.CRY
            | SoundName.CHICKEN
            | SoundName.POOP
            | SoundName.BLOW_POOP
            | SoundName.NEGI
            | SoundName.NEGI_HIT
            | SoundName.NEGI_OUT
            | SoundName.NEGI_BLOCK
            | SoundName.SPIT
            | SoundName.CHARGE
            | SoundName.SLIME
            | SoundName.SLIME_HOP
            | SoundName.SNOT
            | SoundName.FOXFIRE
            | SoundName.FOXFIRE_HIT
            | SoundName.TONGUE
            | SoundName.TONGUE_CATCH
            | SoundName.PIT_DIG
            | SoundName.PIT_DONE
            | SoundName.PIT_FALL
            | SoundName.FOX_LEAP
            | SoundName.SUDDEN
        ):
            return added_recipe(name)
        case _:
            assert_never(name)


def _unexpected(name: SoundName) -> ValueError:
    return ValueError(f"この表の受け持ちではない音: {name}")


def _play(name: SoundName, intensity: int) -> tuple[Part, ...]:
    """原型が初めから持っていた、遊んでいる間の音。"""
    match name:
        case SoundName.PLACE:
            return (
                Tone(f0=300, f1=110, wave=Wave.SQUARE, dur=0.09, vol=0.16),
                Tone(f0=900, f1=600, wave=Wave.TRIANGLE, dur=0.05, vol=0.1),
            )
        case SoundName.EXPLODE:
            blast = (
                Noise(dur=0.5, f0=2200, f1=90, vol=0.75),
                Tone(f0=110, f1=32, wave=Wave.SINE, dur=0.42, vol=0.5),
            )
            # 連鎖したときだけ、少し遅れてもう1つ重ねる。連鎖の数がいくつでも同じ音。
            if intensity > 1:
                return (*blast, Noise(dur=0.35, f0=1200, f1=120, vol=0.4, delay=0.05))
            return blast
        case SoundName.BREAK_BLOCK:
            return (band_noise(dur=0.16, f0=2600, f1=700, vol=0.3, q=1.2),)
        case SoundName.ITEM:
            return tuple(
                Tone(
                    f0=520 * 2 ** (i / 4),
                    wave=Wave.SQUARE,
                    dur=0.08,
                    vol=0.16,
                    delay=i * 0.055,
                )
                for i in range(3)
            )
        case SoundName.HURT:
            return (
                Tone(f0=520, f1=90, wave=Wave.SAWTOOTH, dur=0.3, vol=0.3),
                Noise(dur=0.2, f0=900, f1=200, vol=0.25),
            )
        case SoundName.DIE:
            return (
                *(
                    Tone(
                        f0=440 / 2 ** (i / 3),
                        wave=Wave.SQUARE,
                        dur=0.16,
                        vol=0.22,
                        delay=i * 0.1,
                    )
                    for i in range(4)
                ),
                Noise(dur=0.6, f0=700, f1=60, vol=0.35, delay=0.1),
            )
        case SoundName.JUMP:
            return (Tone(f0=400, f1=820, wave=Wave.TRIANGLE, dur=0.13, vol=0.2),)
        case SoundName.SPECIAL:
            return tuple(
                Tone(
                    f0=392 * 2 ** (s / 12),
                    wave=Wave.SQUARE,
                    dur=0.11,
                    vol=0.17,
                    delay=i * 0.05,
                )
                for i, s in enumerate((0, 3, 7, 10, 12))
            )
        case SoundName.TICK:
            return (Tone(f0=1200, wave=Wave.SQUARE, dur=0.05, vol=0.14),)
        case SoundName.UI:
            return (Tone(f0=760, wave=Wave.SQUARE, dur=0.05, vol=0.12),)
        case _:
            raise _unexpected(name)


def _round_end(name: SoundName) -> tuple[Part, ...]:
    """ラウンドの終わりの音（勝ち・優勝・引き分け）。"""
    match name:
        case SoundName.WIN:
            return tuple(
                Tone(
                    f0=523.25 * 2 ** (s / 12),
                    wave=Wave.TRIANGLE,
                    dur=0.3,
                    vol=0.2,
                    delay=i * 0.11,
                )
                for i, s in enumerate((0, 4, 7, 12, 16, 19))
            )
        case SoundName.CHAMPION:
            return _champion()
        case SoundName.DRAW:
            return tuple(
                Tone(
                    f0=392 * 2 ** (s / 12),
                    wave=Wave.SQUARE,
                    dur=0.35,
                    vol=0.18,
                    delay=i * 0.16,
                )
                for i, s in enumerate((0, -2, -4))
            )
        case _:
            raise _unexpected(name)


def _champion() -> tuple[Part, ...]:
    """優勝のファンファーレ。同じ高さの矩形波と、1オクターブ下の三角波を重ねる。

    並びは（半音の数, 始める秒）。最後に高い所を削ったノイズを重ねる。
    """
    steps = (
        (0, 0),
        (0, 0.12),
        (0, 0.24),
        (4, 0.36),
        (7, 0.48),
        (12, 0.6),
        (7, 0.86),
        (12, 0.98),
        (16, 1.1),
        (19, 1.24),
    )
    parts: list[Part] = []
    for s, d in steps:
        parts.append(
            Tone(
                f0=523.25 * 2 ** (s / 12), wave=Wave.SQUARE, dur=0.26, vol=0.2, delay=d
            )
        )
        parts.append(
            Tone(
                f0=261.6 * 2 ** (s / 12),
                wave=Wave.TRIANGLE,
                dur=0.26,
                vol=0.14,
                delay=d,
            )
        )
    parts.append(
        Noise(
            dur=0.5,
            f0=6000,
            f1=1200,
            vol=0.14,
            filter_type=FilterKind.HIGHPASS,
            delay=1.24,
        )
    )
    return tuple(parts)
