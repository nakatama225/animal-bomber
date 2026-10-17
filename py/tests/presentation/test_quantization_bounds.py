"""取っておく絵の段の数が、それぞれの定数の説明に書いた上限を守るかの検査。

`test_baked.py` は、取っておいた絵と直接描いた絵の差が「段の幅から決まる幅」に収まるかを
見る。段を粗くすると許す幅も一緒に広がるので、そちらだけでは段の数そのものが足りて
いるかは分からない。ここでは、本物の見た目の値をたくさん流して、段に丸めたときのずれが、
定数の説明に書いた上限（色で 255 段のうち 2 段・揺れで 0.25px・赤い光の縁で 0.36px・
火花の半径で 0.125px。どれもマス 60）を超えないことを見る。
"""

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.rules.tuning import BOMB_FUSE
from animal_bomber.domain.state.bomb import Bomb
from animal_bomber.domain.state.item import Item
from animal_bomber.presentation.render.art.bombs import bomb_look
from animal_bomber.presentation.render.art.items import item_look
from animal_bomber.presentation.render.baked.bombs import (
    PULSE_SWING,
    SCALE_LEVELS,
    SPARK_LEVELS,
)
from animal_bomber.presentation.render.baked.items import quantized
from animal_bomber.presentation.render.sprites import level_value, quantize

TILE = 60
"""上限を決めたマスの大きさ（描く面の上限。py/AGENTS.md）。"""

TICKS = range(0, 3600, 7)
"""見る盤面の時刻（1分ぶんを 7 tick おきに）。"""

CELLS = [Cell(col, row) for col in range(1, 22, 5) for row in range(1, 16, 4)]
"""見るマス（揺れと脈打ちの位相はマスの位置でずれる）。"""

EPSILON = 1e-9


def test_札の枠の色のずれは_255段のうち2段まで() -> None:
    """枠の不透明度は 0.7 ＋ 0.3 × 脈打ち（原型の drawItem）。"""
    worst = 0.0
    for cell in CELLS:
        item = Item(EntityId(0), cell, ItemKind.FIRE)
        for now in TICKS:
            look = item_look(item, Tick(now))
            rounded = quantized(look)
            worst = max(worst, abs(rounded.pulse - look.pulse) * 0.3 * 255)
    assert worst <= 1.92 + EPSILON


def test_絵文字の揺れのずれは_0_25pxまで() -> None:
    """揺れは描く面（2倍）の画素1つ（0.5px）ごとの段。いちばん近い段で 0.25px まで。"""
    worst = 0.0
    for cell in CELLS:
        item = Item(EntityId(0), cell, ItemKind.SHOE)
        for now in TICKS:
            look = item_look(item, Tick(now))
            worst = max(worst, abs(quantized(look).bob - look.bob))
    assert worst <= 0.25 + EPSILON


def test_爆弾の赤い光の縁のずれは_0_36pxまで() -> None:
    """赤い光の半径はマスの 0.52 倍に脈打ちの倍率を掛けたもの（原型の drawBomb）。"""
    worst = 0.0
    for fuse in range(1, BOMB_FUSE + 1, 3):
        bomb = Bomb(EntityId(0), Cell(3, 3), 0, 1, Tick(fuse))
        for now in TICKS:
            pulse = bomb_look(bomb, Tick(now)).pulse
            low, high = 1 - PULSE_SWING, 1 + PULSE_SWING
            assert low - EPSILON <= pulse <= high + EPSILON
            level = quantize(pulse, low, high, SCALE_LEVELS)
            rounded = level_value(level, low, high, SCALE_LEVELS)
            worst = max(worst, abs(rounded - pulse) * TILE * 0.52)
    assert worst <= 0.36 + 0.01


def test_火花の半径のずれは_0_125pxまで() -> None:
    """火花の外の円の半径はマスの 0.07＋0.05×揺れ 倍（原型の drawBomb）。"""
    worst = 0.0
    bomb = Bomb(EntityId(0), Cell(3, 3), 0, 1, Tick(BOMB_FUSE))
    for now in TICKS:
        spark = bomb_look(bomb, Tick(now)).spark
        rounded = level_value(quantize(spark, 0, 1, SPARK_LEVELS), 0, 1, SPARK_LEVELS)
        worst = max(worst, abs(rounded - spark) * TILE * 0.05)
    assert worst <= 0.125 + EPSILON
