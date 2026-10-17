"""取っておく絵を初めて描くときの時間を、絵の種類ごとに測る。

`tools/bench_art.py` から使う。

まだ取っていない姿が初めて出たフレームは、その絵を描くぶん遅れる（引っかかり）。種類ごとに、
段の全部を空の入れ物から描いて、1 枚あたりの平均と最大、合計を出す。この値で、絵を
試合の前に描いておくか、初めて出たときに描くかを決める（`render/baked/art.py` の
`BakedArt.prebuild`）。
"""

import time
from collections.abc import Callable

import pygame

from animal_bomber.domain.core.coord import Direction
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.presentation.render.art.animals.body import BodyMotion
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.baked.items import (
    prebuild_items,
    prebuild_melting,
)
from animal_bomber.presentation.render.layout import Layout


def first_draw_times(tile: int) -> dict[str, dict[str, float]]:
    """マス `tile` の、種類ごとの初めて描く時間（ms）。

    種類は、爆弾の部品・爆風（炎と白い芯）・ふだんのアイテム・うさぎの体（歩く姿と
    止まった姿）と、出たときに描く姿の例（撒いている身ぶり・跳び上がり）。
    """
    layout = Layout(tile)
    pygame.display.set_mode(layout.surface_size)
    art = BakedArt(layout)
    report: dict[str, dict[str, float]] = {}

    def timed(name: str, build: Callable[[], None]) -> None:
        before = art.cache.renders
        started = time.perf_counter()
        build()
        total = (time.perf_counter() - started) * 1000
        count = art.cache.renders - before
        report[name] = {
            "sprites": count,
            "total_ms": round(total, 1),
            "mean_ms": round(total / max(1, count), 2),
        }

    timed("bombs", art.bombs.prebuild)
    timed("blasts", art.blasts.prebuild)
    timed("items", lambda: prebuild_items(art.items))
    timed("melting_items", lambda: prebuild_melting(art.items))
    timed("rabbit_walk", lambda: art.bodies.prebuild(Animal.RABBIT))
    worst = 0.0
    for facing in Direction:
        started = time.perf_counter()
        art.bodies.sprite(Animal.RABBIT, facing, BodyMotion(0.3, (0.5, 0.25), None))
        art.bodies.sprite(Animal.RABBIT, facing, BodyMotion(0.0, None, 0.4))
        worst = max(worst, (time.perf_counter() - started) * 1000 / 2)
    report["rabbit_other_poses"] = {"sprites": 8, "max_ms": round(worst, 2)}
    return report
