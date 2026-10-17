"""イベントの中身（状態・アイテム・動物・技の途中の瞬間）から、鳴らす音を引く表。

どの場面で鳴らすか（1 tick ぶんのイベントの並びの見分け）は
`presentation/presenter.py`、ここは種類ごとにどの音を当てるかだけを持つ。どれも
`match` で種類ごとに分け、最後に `assert_never` を置いてある。動物や状態の種類を
足すと、ここで mypy が失敗する。
"""

from typing import assert_never

from animal_bomber.domain.events import Moment
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.presentation.audio.sounds import SoundName


def effect_sound(kind: EffectKind) -> SoundName:
    """状態がかかったときの音。

    バナナ・たまねぎ・落とし穴は専用の音、うんこでかかる状態はまとめて1つ（原型の
    `applyItem`・`pitfallCheck`）。舌が焼き切れて泣くときも、たまねぎと同じ音（原型の
    `tongueBurnCheck`）。跳び上がる・撒いている身ぶりは、かかったことを知らせるイベントを
    出さない（技の音で鳴らす）が、出たときはうんこの音にする（TypeScript 版と同じ）。
    """
    match kind:
        case EffectKind.SLIDE:
            return SoundName.SLIP
        case EffectKind.STUN:
            return SoundName.CRY
        case EffectKind.PITFALL:
            return SoundName.PIT_FALL
        case (
            EffectKind.REVERSE
            | EffectKind.NOBOMB
            | EffectKind.RUNAWAY
            | EffectKind.WEAK
            | EffectKind.AUTOBOMB
            | EffectKind.SLOW
            | EffectKind.LEAP
            | EffectKind.SCATTERING
        ):
            return SoundName.POOP
        case _:
            assert_never(kind)


def taken_sound(kind: ItemKind) -> SoundName | None:
    """アイテムが効いたときの音。悪いアイテムは鳴らさない（None）。

    原型の `applyItem` は、爆弾・火・靴で `item`、チキンで `chicken` を鳴らし、バナナ・
    たまねぎ・うんこは、かかった状態の音（`slip`・`cry`・`poop`）だけを鳴らす。この版
    では状態の音は `EffectApplied` で鳴るので、ここで鳴らすと二重になる。
    """
    match kind:
        case ItemKind.BOMB | ItemKind.FIRE | ItemKind.SHOE:
            return SoundName.ITEM
        case ItemKind.CHICKEN:
            return SoundName.CHICKEN
        case ItemKind.BANANA | ItemKind.ONION | ItemKind.POOP:
            return None
        case _:
            assert_never(kind)


def technique_sounds(animal: Animal | None, special: bool) -> list[SoundName]:
    """その動物がその技を使ったときに鳴らす音（鳴らす順）。鳴らさないなら空。

    とくぎは、どの動物でも共通の音（`SPECIAL`）を先に鳴らし、そのあと動物ごとの音を
    鳴らす（原型の `useSpecial`）。ここに書くのは、技を使えば必ず鳴る音だけ。技が出ても
    鳴らないことがある音（掘る音・炎の音）は、技が出たときの `TechniqueMoment` の側で
    鳴らす（`moment_sound`）。うさぎのとくぎは、うんこを踏んだときと同じ音（原型の
    `rabbitPoroporo`）。動物が分からなければ、とくぎの共通の音だけを鳴らす。

    一列に置く通常技は、ここでは鳴らさない。並べた爆弾の置く音で鳴らす（`Presenter`）。
    """
    if special:
        return [SoundName.SPECIAL, *_special_sounds(animal)]
    tap = _tap_sound(animal)
    return [] if tap is None else [tap]


def _tap_sound(animal: Animal | None) -> SoundName | None:
    match animal:
        # 一列に置く技の音は、置いた爆弾の置く音（原型の `placeLineBombs`）。
        case None | Animal.MOLE | Animal.FOX:
            return None
        # 跳べたときだけ（原型の `hop`）。跳べなければ技を出したイベントが来ない。
        case Animal.RABBIT:
            return SoundName.JUMP
        # 吹けば何も消せなくても鳴る（原型の `elephantSnot`）。
        case Animal.ELEPHANT:
            return SoundName.SNOT
        case Animal.FROG:
            return SoundName.TONGUE
        case _:
            assert_never(animal)


def _special_sounds(animal: Animal | None) -> list[SoundName]:
    match animal:
        # 掘る音は、掘り始めたとき（`DIG_STARTED`）だけ。
        case None | Animal.MOLE:
            return []
        # 撒く輪ごとにも同じ音を鳴らす（`RING_SCATTERED`）。
        case Animal.RABBIT:
            return [SoundName.POOP]
        case Animal.ELEPHANT:
            return [SoundName.CHARGE]
        # 原型は跳び上がる音を鳴らし、炎を出したとき（`CHASER_CAST`）だけ炎の音を
        # 続ける。
        case Animal.FOX:
            return [SoundName.FOX_LEAP]
        case Animal.FROG:
            return [SoundName.SLIME]
        case _:
            assert_never(animal)


def moment_sound(moment: Moment) -> SoundName:
    """技の途中で起きたことに当てる音（原型の、それぞれの瞬間の専用の音）。"""
    match moment:
        case Moment.TONGUE_CAUGHT:
            return SoundName.TONGUE_CATCH
        case Moment.DIG_STARTED:
            return SoundName.PIT_DIG
        case Moment.PIT_DUG:
            return SoundName.PIT_DONE
        case Moment.SLIME_HOPPED:
            return SoundName.SLIME_HOP
        case Moment.ITEMS_SPAT:
            return SoundName.SPIT
        case Moment.RAMMED:
            return SoundName.CHARGE
        case Moment.CHASER_CAST:
            return SoundName.FOXFIRE
        case Moment.CHASER_HIT:
            return SoundName.FOXFIRE_HIT
        case Moment.RING_SCATTERED:
            return SoundName.POOP
        case _:
            assert_never(moment)
