"""盤面の絵を取っておいて貼るものを、1つのマスの大きさについてまとめる。"""

from collections.abc import Iterable

from animal_bomber.domain.rules.animals import Animal
from animal_bomber.presentation.render.baked.board import BoardSprites
from animal_bomber.presentation.render.baked.bodies import BodySprites
from animal_bomber.presentation.render.baked.bombs import BlastSprites, BombSprites
from animal_bomber.presentation.render.baked.items import (
    ItemSprites,
    prebuild_items,
    prebuild_melting,
)
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.sprites import SpriteCache


class BakedArt:
    """マスの大きさ `layout` の、盤面の絵（床・アイテム・爆弾・爆風・動物の体）。

    取っておく絵はどれも同じ入れ物（`cache`）に入る。マスの大きさを変えたら、作り直す。
    """

    def __init__(self, layout: Layout, cache: SpriteCache | None = None) -> None:
        self.layout = layout
        self.cache = cache if cache is not None else SpriteCache()
        self.board = BoardSprites(layout, self.cache)
        self.items = ItemSprites(layout, self.cache)
        self.bombs = BombSprites(layout, self.cache)
        self.blasts = BlastSprites(layout, self.cache)
        self.bodies = BodySprites(layout.tile, self.cache)

    def prebuild(self, animals: Iterable[Animal]) -> None:
        """試合で使う絵を先に描いておく（初めて出たときに描くと、そのフレームが遅れる）。

        段の数で決まる組み合わせの全部（爆弾・爆風・アイテム。点滅するうんこを含む）と、
        試合に出る動物の歩く姿と止まった姿を描く。ぞうが出るなら、鼻水で溶けていくうんこも
        描く。撒いている身ぶりと跳び上がりの姿は、出たときに描く（1匹につき1秒ほどしか
        出ず、組み合わせが多い。初めて描く1枚はマス 60 で 6ms ほど）。

        マス 60・うさぎだけで 1 秒ほどかかる（`tools/bench_art.py --first-draw`）。
        取っておいた絵はラウンドをまたいで使えるので、マスの大きさが変わらなければ
        描き直さない。
        """
        chosen = list(dict.fromkeys(animals))
        self.bombs.prebuild()
        self.blasts.prebuild()
        prebuild_items(self.items)
        if Animal.ELEPHANT in chosen:
            prebuild_melting(self.items)
        for animal in chosen:
            self.bodies.prebuild(animal)
