"""原型が、あとから足した効果音（アイテム・葱ボン・技・延長戦）。

原型（`legacy/animal-bomber.html` の `SE`）の数値と式をそのまま写した。原型の `SE` は、
初めからあった音と、あとから足した音を分けて書いてあり、この版もその分け方で
`recipes.py` とここに分けた。動物を足したり技を変えたりしたときに、音の表で書き足す
のはこちら。⚠️ 式を書き換えない理由は `recipes.py` の説明と同じ。
"""

from animal_bomber.presentation.audio.parts import (
    FilterKind,
    Noise,
    Part,
    Tone,
    Wave,
    band_noise,
)
from animal_bomber.presentation.audio.sounds import SoundName


def added_recipe(name: SoundName) -> tuple[Part, ...]:
    """あとから足した効果音1つの部品を、原型が作る順に返す。

    この表の受け持ちでない音なら例外にする（振り分けは `recipes.py` の `recipe`）。
    """
    match name:
        case (
            SoundName.SLIP
            | SoundName.CRY
            | SoundName.CHICKEN
            | SoundName.POOP
            | SoundName.BLOW_POOP
        ):
            return _items(name)
        case (
            SoundName.NEGI
            | SoundName.NEGI_HIT
            | SoundName.NEGI_OUT
            | SoundName.NEGI_BLOCK
            | SoundName.SUDDEN
        ):
            return _late_round(name)
        case SoundName.SPIT:
            return (
                Tone(f0=330, f1=660, wave=Wave.TRIANGLE, dur=0.11, vol=0.15),
                Tone(f0=990, wave=Wave.SQUARE, dur=0.05, vol=0.08, delay=0.06),
            )
        case SoundName.CHARGE:
            return (
                Noise(
                    dur=0.45, f0=700, f1=180, vol=0.26, filter_type=FilterKind.LOWPASS
                ),
                Tone(f0=130, f1=220, wave=Wave.SAWTOOTH, dur=0.4, vol=0.22),
                Tone(f0=900, f1=400, wave=Wave.SQUARE, dur=0.1, vol=0.1),
            )
        case SoundName.SLIME:
            return (
                Tone(f0=200, f1=520, wave=Wave.SINE, dur=0.22, vol=0.2),
                band_noise(dur=0.14, f0=900, f1=2200, vol=0.1, q=1.4),
            )
        case SoundName.SLIME_HOP:
            return (Tone(f0=420, f1=700, wave=Wave.SINE, dur=0.09, vol=0.13),)
        case SoundName.SNOT:
            return (
                band_noise(dur=0.28, f0=2600, f1=500, vol=0.2, q=1.1),
                Tone(f0=220, f1=90, wave=Wave.SAWTOOTH, dur=0.22, vol=0.14),
            )
        # 狐火：妖しい青い炎。3つの音が、それぞれ半音5つ上へずれていく。
        case SoundName.FOXFIRE:
            return (
                *(
                    Tone(
                        f0=330 * 2 ** (s / 12),
                        f1=330 * 2 ** ((s + 5) / 12),
                        wave=Wave.SINE,
                        dur=0.5,
                        vol=0.15,
                        delay=i * 0.06,
                    )
                    for i, s in enumerate((0, 7, 12))
                ),
                band_noise(dur=0.6, f0=2600, f1=700, vol=0.12, q=2),
            )
        case SoundName.FOXFIRE_HIT:
            return (
                Tone(f0=900, f1=180, wave=Wave.SINE, dur=0.3, vol=0.24),
                band_noise(dur=0.25, f0=3000, f1=600, vol=0.18, q=1.5),
            )
        # かえるの舌
        case SoundName.TONGUE:
            return (Tone(f0=700, f1=1300, wave=Wave.SINE, dur=0.13, vol=0.16),)
        case SoundName.TONGUE_CATCH:
            return (
                Tone(f0=1300, f1=600, wave=Wave.SINE, dur=0.12, vol=0.18),
                Tone(f0=1800, wave=Wave.SQUARE, dur=0.05, vol=0.09, delay=0.1),
            )
        case SoundName.PIT_DIG | SoundName.PIT_DONE | SoundName.PIT_FALL:
            return _pit(name)
        # キツネ跳び：跳び上がる音 → 滞空 → 着地。
        case SoundName.FOX_LEAP:
            return (
                Tone(f0=420, f1=1150, wave=Wave.TRIANGLE, dur=0.22, vol=0.24),
                Tone(f0=1400, f1=900, wave=Wave.SQUARE, dur=0.1, vol=0.1, delay=0.2),
                Tone(f0=260, f1=150, wave=Wave.SINE, dur=0.14, vol=0.2, delay=0.72),
                Noise(dur=0.12, f0=900, f1=200, vol=0.16, delay=0.74),
            )
        case _:
            raise ValueError(f"この表の受け持ちではない音: {name}")


def _pit(name: SoundName) -> tuple[Part, ...]:
    """もぐらの落とし穴：ザクザク掘る → 仕掛け完了 → 誰かが落ちる。"""
    match name:
        case SoundName.PIT_DIG:
            parts: list[Part] = []
            for i in range(5):
                parts.append(
                    band_noise(
                        dur=0.16, f0=1500, f1=300, vol=0.15, q=1.5, delay=i * 0.28
                    )
                )
                parts.append(
                    Tone(
                        f0=170,
                        f1=90,
                        wave=Wave.TRIANGLE,
                        dur=0.12,
                        vol=0.1,
                        delay=i * 0.28,
                    )
                )
            return tuple(parts)
        case SoundName.PIT_DONE:
            return (
                Tone(f0=150, f1=80, wave=Wave.SINE, dur=0.2, vol=0.18),
                Tone(f0=600, wave=Wave.SQUARE, dur=0.05, vol=0.07, delay=0.16),
            )
        case SoundName.PIT_FALL:
            return (
                Tone(f0=700, f1=70, wave=Wave.SINE, dur=0.55, vol=0.3),
                Noise(
                    dur=0.5, f0=1200, f1=120, vol=0.24, filter_type=FilterKind.LOWPASS
                ),
                *(
                    Tone(
                        f0=330 * 2 ** (sc / 12),
                        wave=Wave.TRIANGLE,
                        dur=0.18,
                        vol=0.14,
                        delay=0.15 + i * 0.1,
                    )
                    for i, sc in enumerate((0, -4, -8))
                ),
            )
        case _:
            raise ValueError(f"落とし穴の音ではない: {name}")


def _items(name: SoundName) -> tuple[Part, ...]:
    """アイテムの音（原型が、あとから足した効果音）。"""
    match name:
        case SoundName.SLIP:
            return (
                Tone(f0=1100, f1=220, wave=Wave.SINE, dur=0.42, vol=0.22),
                band_noise(dur=0.3, f0=3000, f1=800, vol=0.14, q=2),
            )
        case SoundName.CRY:
            return tuple(
                Tone(
                    f0=660 - i * 90,
                    f1=520 - i * 90,
                    wave=Wave.SAWTOOTH,
                    dur=0.22,
                    vol=0.16,
                    delay=i * 0.16,
                )
                for i in range(3)
            )
        case SoundName.CHICKEN:
            return tuple(
                Tone(
                    f0=440 * 2 ** (s / 12),
                    wave=Wave.TRIANGLE,
                    dur=0.16,
                    vol=0.2,
                    delay=i * 0.07,
                )
                for i, s in enumerate((0, 5, 9, 12))
            )
        case SoundName.POOP:
            return (
                Tone(f0=220, f1=55, wave=Wave.SAWTOOTH, dur=0.45, vol=0.24),
                Noise(
                    dur=0.35, f0=500, f1=90, vol=0.22, filter_type=FilterKind.LOWPASS
                ),
            )
        case SoundName.BLOW_POOP:
            return (
                Noise(dur=0.22, f0=700, f1=160, vol=0.2),
                Tone(f0=300, f1=520, wave=Wave.SINE, dur=0.18, vol=0.14),
            )
        case _:
            raise ValueError(f"この表の受け持ちではない音: {name}")


def _late_round(name: SoundName) -> tuple[Part, ...]:
    """葱ボン（倒れたプレイヤーが外周から葱を投げる）と延長戦の音。どちらも段階 8。"""
    match name:
        case SoundName.NEGI:
            return (
                Tone(f0=1500, f1=640, wave=Wave.TRIANGLE, dur=0.15, vol=0.2),
                Noise(
                    dur=0.1, f0=4000, f1=1200, vol=0.1, filter_type=FilterKind.HIGHPASS
                ),
            )
        case SoundName.NEGI_HIT:
            return (
                *(
                    Tone(
                        f0=523 * 2 ** (s / 12),
                        wave=Wave.SQUARE,
                        dur=0.16,
                        vol=0.2,
                        delay=i * 0.06,
                    )
                    for i, s in enumerate((0, 4, 7, 12, 16))
                ),
                Noise(dur=0.25, f0=2200, f1=400, vol=0.2),
            )
        case SoundName.NEGI_OUT:
            return tuple(
                Tone(
                    f0=392 * 2 ** (s / 12),
                    wave=Wave.SQUARE,
                    dur=0.2,
                    vol=0.16,
                    delay=i * 0.12,
                )
                for i, s in enumerate((0, -3, -7))
            )
        case SoundName.NEGI_BLOCK:
            return (
                Tone(f0=180, f1=90, wave=Wave.SQUARE, dur=0.1, vol=0.22),
                band_noise(dur=0.09, f0=1600, f1=500, vol=0.16, q=3),
            )
        case SoundName.SUDDEN:
            return (
                *(
                    Tone(
                        f0=880 if i % 2 else 660,
                        wave=Wave.SQUARE,
                        dur=0.14,
                        vol=0.24,
                        delay=i * 0.17,
                    )
                    for i in range(4)
                ),
                Tone(f0=80, f1=40, wave=Wave.SINE, dur=0.9, vol=0.35, delay=0.1),
            )
        case _:
            raise ValueError(f"この表の受け持ちではない音: {name}")
