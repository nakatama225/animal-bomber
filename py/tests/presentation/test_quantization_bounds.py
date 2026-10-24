"""取っておく絵の段の数が、それぞれの定数の説明に書いた上限を守るかの検査。

`test_baked.py` は、取っておいた絵と直接描いた絵の差が「段の幅から決まる幅」に収まるかを
見る。段を粗くすると許す幅も一緒に広がるので、そちらだけでは段の数そのものが足りて
いるかは分からない。ここでは、本物の見た目の値をたくさん流して、段に丸めたときのずれが、
定数の説明に書いた上限（色で 255 段のうち 2 段・揺れで 0.25px・爆弾の脈打ちで赤い光の
半径 0.30px と火花の外の縁 0.38px・火花の半径で 0.125px・掘りかけの穴の半径で
横 0.22px と縦 0.13px・ゲージと外周の鍋の撃つ間隔の帯の長さで 0.25px・火の玉の半径と
芯の縦の半径で 0.25px・四角い粒の一辺と爆風のちらつく芯の一辺で 0.25px・位置で 0.5px。
どれもマス 60）を超えないことを見る。ゲージ・帯の長さ・穴の大きさ・芯の太さは、試合で
出る値を全部流す。

⚠️ 鼻水で溶けている間のアイテムの段（`baked/items.py` の `MELT_PULSE_LEVELS`・
`MELT_BOB_LEVELS`）は、ここに入れていない（取っておいた絵を画素で比べる `test_baked.py`
には入っている）。
"""

import pygame

from animal_bomber.domain.abilities.mole import DIG_TIME, HOLD_TIME
from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal, stats_of
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.rules.tuning import (
    BLAST_DURATION,
    BOMB_FUSE,
    LEEK_FIRST_COOLDOWN,
)
from animal_bomber.domain.state.bomb import Blast, Bomb
from animal_bomber.domain.state.item import Item
from animal_bomber.presentation.cosmetic_rng import CosmeticRng, ScriptedRandom
from animal_bomber.presentation.render.art.animals.mole import dig_progress
from animal_bomber.presentation.render.art.blasts import flicker_size, progress_of
from animal_bomber.presentation.render.art.bombs import bomb_look
from animal_bomber.presentation.render.art.foxfires import core_width, flame_flicker
from animal_bomber.presentation.render.art.items import item_look
from animal_bomber.presentation.render.art.negibons import BAND_WIDTH, band_ratio
from animal_bomber.presentation.render.art.particles import ParticleLook
from animal_bomber.presentation.render.baked.actors import (
    CORE_LEVELS,
    CORE_RANGE,
    FLAME_LEVELS,
    FLAME_RANGE,
)
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.baked.bombs import (
    PULSE_SWING,
    SCALE_LEVELS,
    SPARK_LEVELS,
    flicker_side,
)
from animal_bomber.presentation.render.baked.digging import DIG_LEVELS
from animal_bomber.presentation.render.baked.items import quantized
from animal_bomber.presentation.render.baked.negibons import BAND_STEP, band_level
from animal_bomber.presentation.render.baked.particles import particle_side
from animal_bomber.presentation.render.baked.techniques import gauge_level, snap
from animal_bomber.presentation.render.canvas.surface import SUPERSAMPLE
from animal_bomber.presentation.render.layout import TILE_MAX, TILE_MIN, Layout
from animal_bomber.presentation.render.sprites import level_value, quantize

TILE = 60
"""上限を決めたマスの大きさ（描く面の上限。py/AGENTS.md）。"""

TIMES = tuple(quarter / 4 for quarter in range(0, 3600 * 4, 7))
"""見る描く時刻（1分ぶんを 7/4 tick おきに）。

ゲーム速度が整数でないときの描く時刻は 1/4 tick 刻みの小数（`views/player.py` の
`drawn_time`）なので、tick の整数だけでなく、その間の時刻でも上限を確認する。
"""

CELLS = [Cell(col, row) for col in range(1, 22, 5) for row in range(1, 16, 4)]
"""見るマス（揺れと脈打ちの位相はマスの位置でずれる）。"""

EPSILON = 1e-9


def test_札の枠の色のずれは_255段のうち2段まで() -> None:
    """枠の不透明度は 0.7 ＋ 0.3 × 脈打ち（原型の drawItem）。"""
    worst = 0.0
    for cell in CELLS:
        item = Item(EntityId(0), cell, ItemKind.FIRE)
        for now in TIMES:
            look = item_look(item, now)
            rounded = quantized(look)
            worst = max(worst, abs(rounded.pulse - look.pulse) * 0.3 * 255)
    assert worst <= 1.92 + EPSILON


def test_絵文字の揺れのずれは_0_25pxまで() -> None:
    """揺れは描く面（2倍）の画素1つ（0.5px）ごとの段。いちばん近い段で 0.25px まで。"""
    worst = 0.0
    for cell in CELLS:
        item = Item(EntityId(0), cell, ItemKind.SHOE)
        for now in TIMES:
            look = item_look(item, now)
            worst = max(worst, abs(quantized(look).bob - look.bob))
    assert worst <= 0.25 + EPSILON


def test_爆弾の脈打ちのずれは_赤い光の半径で0_30px_火花の外の縁で0_38pxまで() -> None:
    """倍率は爆弾の中心のまわりに掛かる（原型の drawBomb）。

    赤い光の半径はマスの 0.52 倍。中心からいちばん遠いのは火花の外の縁で、マスの
    0.64 倍（火花の円の中心までの √(0.17² + 0.49²) ≒ 0.52 倍に、半径の上限の 0.12 倍を
    足したもの）。
    """
    worst = 0.0
    for fuse in range(1, BOMB_FUSE + 1, 3):
        bomb = Bomb(EntityId(0), Cell(3, 3), 0, 1, Tick(fuse))
        for now in TIMES:
            pulse = bomb_look(bomb, now).pulse
            low, high = 1 - PULSE_SWING, 1 + PULSE_SWING
            assert low - EPSILON <= pulse <= high + EPSILON
            level = quantize(pulse, low, high, SCALE_LEVELS)
            rounded = level_value(level, low, high, SCALE_LEVELS)
            worst = max(worst, abs(rounded - pulse))
    assert worst * TILE * 0.52 <= 0.31
    assert worst * TILE * 0.64 <= 0.38


def test_火花の半径のずれは_0_125pxまで() -> None:
    """火花の外の円の半径はマスの 0.07＋0.05×揺れ 倍（原型の drawBomb）。"""
    worst = 0.0
    bomb = Bomb(EntityId(0), Cell(3, 3), 0, 1, Tick(BOMB_FUSE))
    for now in TIMES:
        spark = bomb_look(bomb, now).spark
        rounded = level_value(quantize(spark, 0, 1, SPARK_LEVELS), 0, 1, SPARK_LEVELS)
        worst = max(worst, abs(rounded - spark) * TILE * 0.05)
    assert worst <= 0.125 + EPSILON


def test_掘りかけの穴の半径のずれは_横0_22px_縦0_13pxまで() -> None:
    """穴の半径はマスの（0.1＋0.22×進み）倍と（0.05＋0.13×進み）倍（原型の値）。

    進みは掘り終わるまでの残り（0〜90 tick）で決まるので、全部流す。
    """
    worst_x = worst_y = 0.0
    for left in range(DIG_TIME + 1):
        k = dig_progress(Tick(left))
        rounded = level_value(quantize(k, 0, 1, DIG_LEVELS), 0, 1, DIG_LEVELS)
        worst_x = max(worst_x, abs(rounded - k) * TILE * 0.22)
        worst_y = max(worst_y, abs(rounded - k) * TILE * 0.13)
    assert worst_x <= 0.22 + EPSILON
    assert worst_y <= 0.13 + EPSILON


def test_ゲージの長さのずれは_0_25pxまで() -> None:
    """長押し・落とし穴・掘る身ぶりのゲージを、試合で出る溜まりと残りで全部流す。"""
    lengths = []
    for animal in Animal:
        hold = stats_of(animal).hold_ticks
        lengths += [TILE * 0.62 * min(1, held / hold) for held in range(hold + 1)]
    lengths += [TILE * 0.6 * left / HOLD_TIME for left in range(HOLD_TIME + 1)]
    lengths += [TILE * 0.6 * dig_progress(Tick(left)) for left in range(DIG_TIME + 1)]
    worst = max(abs(gauge_level(length) / SUPERSAMPLE - length) for length in lengths)
    assert worst <= 0.25 + EPSILON


def test_撃つ間隔の帯の長さのずれは_0_25pxまで() -> None:
    """外周の鍋の帯（マス × 0.56 × 残り ÷ 撃つ間隔）を、とりうる残りで全部流す。

    残りは外周へ回った直後の 3.5 秒（`LEEK_FIRST_COOLDOWN`）から 1 tick まで。マスの
    大きさの範囲（26〜60）の全部で見る（帯の長さはマスに比例する）。
    """
    worst = 0.0
    for tile in range(TILE_MIN, TILE_MAX + 1):
        for left in range(1, LEEK_FIRST_COOLDOWN + 1):
            length = tile * BAND_WIDTH * band_ratio(Tick(left))
            worst = max(worst, abs(band_level(tile, Tick(left)) * BAND_STEP - length))
    assert worst <= 0.25 + EPSILON


def test_火の玉と芯の大きさのずれは_0_25pxまで() -> None:
    """火の玉の半径はマスの 0.6 × 揺れ 倍、芯の縦の半径は太さの 1.15 倍（原型の値）。"""
    worst_flame = worst_core = 0.0
    low, high = (value * TILE for value in CORE_RANGE)
    for quarter in range(3600 * 4):
        now = quarter / 4
        flicker = flame_flicker(now)
        level = quantize(flicker, *FLAME_RANGE, FLAME_LEVELS)
        rounded = level_value(level, *FLAME_RANGE, FLAME_LEVELS)
        worst_flame = max(worst_flame, abs(rounded - flicker) * TILE * 0.6)
        width = core_width(TILE, now)
        rounded_width = level_value(
            quantize(width, low, high, CORE_LEVELS), low, high, CORE_LEVELS
        )
        worst_core = max(worst_core, abs(rounded_width - width) * 1.15)
    assert worst_flame <= 0.25 + EPSILON
    assert worst_core <= 0.25 + EPSILON


def test_四角い粒の一辺のずれは_0_25pxまで() -> None:
    """一辺は原型の乱数（3〜9px）。描く面の画素（0.5px）ごとに丸める（`particle_side`）。"""
    worst = 0.0
    for step in range(601):
        size = 3 + step * 0.01
        worst = max(worst, abs(particle_side(size) / SUPERSAMPLE - size))
    assert worst <= 0.25 + EPSILON


def test_爆風のちらつく芯の一辺のずれは_0_25pxまで() -> None:
    """一辺はマスの (0.16 ＋ 0.2 × 乱数) × 残りの割合 倍（原型の drawBlast）。

    描く面の画素（0.5px）ごとに丸める（`flicker_side`）。残りは全部、乱数は 0.005 おきに
    流す。
    """
    worst = 0.0
    for remaining in range(1, BLAST_DURATION + 1):
        k = progress_of(remaining)
        for step in range(201):
            rng = CosmeticRng(ScriptedRandom([step / 200]))
            length = flicker_size(TILE, k, rng)
            worst = max(worst, abs(flicker_side(length) / SUPERSAMPLE - length))
    assert worst <= 0.25 + EPSILON


def test_位置は_いちばん近い整数のpxに丸める() -> None:
    """体・舌・粒子の位置と画面の揺れのずれ（`snap`）。ずれは 0.5px まで。"""
    assert [snap(0.6), snap(-0.6), snap(0.4)] == [1, -1, 0]
    worst = max(abs(snap(step / 100) - step / 100) for step in range(-300, 301))
    assert worst <= 0.5 + EPSILON


class Test描く所がこの丸めを使う:
    """上の丸めの関数を、描く所が通っていることを、取っておいた絵の鍵で見る。

    鍵の一辺は、描く面の画素（0.5px）の数。2倍した一辺の小数部が 0.5 以上になる大きさに
    して、いちばん近い段（切り上げ）と切り捨てで鍵が違うようにする。
    """

    def test_四角い粒(self) -> None:
        """一辺 5.3px は描く面で 10.6 画素。いちばん近い段は 11（切り捨てなら 10）。"""
        art = BakedArt(Layout(50))
        target = pygame.Surface(art.layout.surface_size)
        art.particles.draw(target, ParticleLook(4.0, 6.0, 1.0, "#a2703f", 5.3))
        keys = dict(art.cache.entries())
        assert ("particle-square", "#a2703f", 11) in keys
        assert ("particle-square", "#a2703f", 10) not in keys

    def test_爆風のちらつく芯(self) -> None:
        """描く面で 18.7 画素になる乱数を差す。

        いちばん近い段は 19（切り捨てなら 18）。
        """
        layout = Layout(50)
        remaining = Tick(20)
        k = progress_of(remaining)
        value = (18.7 / SUPERSAMPLE / (layout.tile * k) - 0.16) / 0.2
        assert 0 <= value < 1
        art = BakedArt(layout)
        target = pygame.Surface(layout.surface_size)
        blast = Blast(EntityId(1), Cell(6, 7), 0, False, remaining)
        art.blasts.draw(target, blast, CosmeticRng(ScriptedRandom([value])))
        keys = dict(art.cache.entries())
        assert ("blast-flicker", remaining, 19) in keys
        assert ("blast-flicker", remaining, 18) not in keys
