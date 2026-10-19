"""盤面の絵を取っておいて貼るものを、1つのマスの大きさについてまとめる。"""

from collections.abc import Iterable

from animal_bomber.domain.rules.animals import Animal, stats_of
from animal_bomber.presentation.render.art.player import BLINK_ALPHA, IN_BLOCK_ALPHA
from animal_bomber.presentation.render.art.player_marks import special_emoji
from animal_bomber.presentation.render.baked.actors import FoxfireSprites, SlimeSprites
from animal_bomber.presentation.render.baked.board import BoardSprites
from animal_bomber.presentation.render.baked.bodies import BodySprites
from animal_bomber.presentation.render.baked.bombs import BlastSprites, BombSprites
from animal_bomber.presentation.render.baked.digging import DigSprites
from animal_bomber.presentation.render.baked.items import (
    ItemSprites,
    prebuild_items,
    prebuild_melting,
)
from animal_bomber.presentation.render.baked.negibons import NegibonSprites
from animal_bomber.presentation.render.baked.particles import ParticleSprites
from animal_bomber.presentation.render.baked.players import PlayerSprites
from animal_bomber.presentation.render.baked.techniques import TongueSprites
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.sprites import SpriteCache


class BakedArt:
    """マスの大きさ `layout` の、盤面の絵（床・アイテム・爆弾・爆風・プレイヤーなど）。

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
        self.tongues = TongueSprites(layout, self.cache)
        self.digs = DigSprites(layout, self.cache)
        self.players = PlayerSprites(
            layout, self.cache, self.bodies, self.tongues, self.digs
        )
        self.slimes = SlimeSprites(layout, self.cache)
        self.foxfires = FoxfireSprites(layout, self.cache)
        self.negibons = NegibonSprites(layout, self.cache)
        self.particles = ParticleSprites(layout, self.cache)

    def prebuild(self, animals: Iterable[Animal]) -> None:
        """試合で使う絵を先に描いておく（初めて出たときに描くと、そのフレームが遅れる）。

        床と壁のマス、段の数で決まる組み合わせの全部（爆弾・爆風・アイテム。点滅する
        うんこを含む）と、試合に出る動物ごとに次を描く。

        - 歩く姿と止まった姿・接地影と輪を、ふだんの濃さと無敵の点滅の薄さで（被弾の
          あとの 1.25 秒は、脚を振りながら点滅する）
        - ブロックを通り抜ける動物は、ブロックの中の薄さでも
        - とくぎの印と、長押しのゲージの長さの全部（チキンを拾うと出る）
        - 落とし穴を掘る動物が出るなら、ほかの動物の、落とし穴にはまって止まった姿と
          穴の縁（ふだんの濃さと、はまったまま被弾した点滅の薄さで）・目印の顔・残りの
          ゲージ、掘る身ぶりの絵
        - 舌の部品と粘膜爆弾の形の全部（かえる）・追いかける炎（きつね）
        - ぞうが出るなら、鼻水で溶けていくうんこ
        - 外周の鍋（動物ごと）と、撃つ間隔の帯の長さの全部・🌿・撃つ向きの点線と葱の
          4向き（どの試合でも、倒れたプレイヤーは外周へ回る）

        撒いている身ぶりと跳び上がりの姿、状態の印の組み合わせは、出たときに描く（1匹に
        つき1秒ほどしか出ないか、組み合わせが多い）。

        かかる時間（`tools/bench_render.py --first-draw` の `prebuild_rabbit`・
        `prebuild_all`）は、マス 60 で、うさぎだけ 1.45 秒（1288 枚）・5匹全部 4.66 秒
        （2685 枚。2026-10-19 に測った。外周の鍋と葱は 5匹ぶんで 101 枚・25 ms）。
        体の絵（1枚 4ms ほど）を点滅の薄さでも描くようにして、体の枚数が倍になったのが
        おもな増え方（技の部品を足す前は、うさぎだけ 1.1 秒・5匹全部 2.4 秒）。取って
        おいた絵はラウンドをまたいで使えるので、マスの大きさが変わらなければ描き直さない。
        """
        chosen = list(dict.fromkeys(animals))
        self.board.prebuild()
        self.bombs.prebuild()
        self.blasts.prebuild()
        prebuild_items(self.items)
        if Animal.ELEPHANT in chosen:
            prebuild_melting(self.items)
        pits = Animal.MOLE in chosen
        self.players.prebuild_gauges(pits=pits)
        for animal in chosen:
            alphas = [1.0, BLINK_ALPHA]
            if stats_of(animal).passes_soft_blocks:
                alphas.append(IN_BLOCK_ALPHA)
            for alpha in alphas:
                self.bodies.prebuild(animal, alpha)
            self.players.prebuild(animal, tuple(alphas))
            self.players.marks(special_emoji(animal), 1.0)
            if pits and animal is not Animal.MOLE:
                # はまったまま被弾すると点滅する（穴の中でも爆風は当たる）。
                self.bodies.prebuild_pit(animal)
                self.bodies.prebuild_pit(animal, BLINK_ALPHA)
        if pits:
            self.digs.prebuild()
        if Animal.FROG in chosen:
            self.tongues.prebuild()
            self.slimes.prebuild()
        if Animal.FOX in chosen:
            self.foxfires.prebuild()
        self.negibons.prebuild(chosen)
