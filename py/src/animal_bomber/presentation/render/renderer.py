"""1フレームの絵を、取っておいた絵を貼って描く（原型の draw）。

並べる順・画面の揺れ・見た目の乱数を引く順は、手本の `art/frame.py` の draw_frame と
同じ（背景 → 画面の揺れ → 床と壁 → アイテム → 爆弾 → 爆風 → プレイヤー（上にいる順）→
炎 → 粘膜爆弾 → 粒子）。描く関数を直接呼ぶ手本と違い、ここは取っておいた絵
（`render/baked/`）を貼る。最後に、盤面の上の帯（`band.py`）を貼る。

試合の状態（`WorldState`・`MatchState`）は読むだけで書き換えない。試合の状態に無い値
（粒子・画面の揺れ・歩いた距離など）は `Visuals` から読む（`scene/tracker.py` の
`SceneTracker` が数える）。

## 画面の揺れ

原型と同じく、揺れが 0.2 を超えていれば、描くたびに見た目の乱数を横・縦の順に2つ引いて
ずらす（決着のあとの待ちの間も、止まった揺れの幅のまま揺らす）。ずれは整数の px に丸めて
貼る（丸めのずれは 0.5px まで。取っておいた絵はマスの左上からの小数のずれが同じ所に
貼るので、整数でずらせば絵は変わらない）。

## 落とし穴の、不透明度の戻し忘れ

原型の drawPlayer は、落とし穴にはまったプレイヤーを描くと、不透明度を戻さずに帰る
（`art/player.py` の draw_player の注記）。そのフレームのそのあとに描くもののうち、
不透明度を自分で決めないもの（あとに描くプレイヤーとその舌・掘る身ぶり、炎の火の玉）は、
その不透明度で描かれる。手本の draw_frame は命令どおりに写してあるので、ここも同じく、
プレイヤーを貼るたびに返る不透明度を、次のプレイヤーと炎へ渡す。

⚠️ 原型では、落とし穴にはまったプレイヤーが同じフレームに2体いて、先に描くほうが点滅して
いると、フレームを描き終えたあとも canvas の不透明度が戻らず、次のフレームからは背景や
床まで薄く描かれる（前のフレームの絵が透けて残る）。この版はフレームごとに描き直すので、
フレームをまたいでは写さない（docs/08 の「原型と違うまま残した所」）。
"""

from collections.abc import Sequence
from typing import Protocol, assert_never

import pygame

from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.state.actors import (
    BurntTongue,
    Foxfire,
    Pit,
    Scatter,
    SlimeBomb,
)
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.player import PlayerId, is_alive
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.render.art.foxfires import FoxfireLook, TrailMark
from animal_bomber.presentation.render.art.frame import draw_background, shake_offset
from animal_bomber.presentation.render.art.particles import ParticleLook
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.baked.board import BoardLayer
from animal_bomber.presentation.render.baked.techniques import snap
from animal_bomber.presentation.render.band import Band
from animal_bomber.presentation.render.canvas.surface import SurfaceCanvas
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.views.actors import slime_look
from animal_bomber.presentation.render.views.player import TrackedMotion, player_look


class Visuals(Protocol):
    """試合の状態に無い、見た目だけの値（`scene/tracker.py` の `SceneTracker`）。"""

    @property
    def shake(self) -> float:
        """画面の揺れの幅（px。原型の shakeAmt）。"""
        ...

    @property
    def particles(self) -> Sequence[ParticleLook]:
        """粒子（描く順）。"""
        ...

    def motion(self, player: PlayerId) -> TrackedMotion:
        """プレイヤーの動きの値。"""
        ...

    def slime(self, actor: SlimeBomb) -> tuple[tuple[float, float], bool]:
        """粘膜爆弾を投げた位置（マス）と、着地してから跳ねたか。"""
        ...

    def trail(self, actor: Foxfire, now: Tick) -> tuple[TrailMark, ...]:
        """炎の通った跡。"""
        ...


class Renderer:
    """1フレームの絵を描く。

    `art` は試合の前に描いておいた絵（`BakedArt.prebuild`）、`rng` は見た目の乱数
    （画面の揺れ・爆風のちらつき・被弾の揺れ）。`band` を省くと、帯の高さが
    `art.layout.band` の帯を作る（高さ 0 なら帯を描かない）。
    """

    def __init__(
        self, art: BakedArt, rng: CosmeticRng | None = None, band: Band | None = None
    ) -> None:
        self.art = art
        self._rng = rng if rng is not None else CosmeticRng()
        layout = art.layout
        self._band = band
        if band is None and layout.band > 0:
            self._band = Band(layout.band)
        self._background = background(layout)
        self._board = BoardLayer(art.board, layout)

    @property
    def layout(self) -> Layout:
        """描く面の寸法。"""
        return self.art.layout

    def draw(
        self,
        target: pygame.Surface,
        world: WorldState,
        match: MatchState,
        visuals: Visuals,
    ) -> None:
        """いまの盤面を `target`（描く面。アルファの桁の無い面）に描く。"""
        art, rng, now = self.art, self._rng, world.now
        moved = shake_offset(visuals.shake, rng)
        offset = (0, 0) if moved is None else (snap(moved[0]), snap(moved[1]))
        board = self._board
        if offset == (0, 0):
            target.blit(board.still(world.board, self._background), (0, 0))
        else:
            # 背景は揺らさない（`art/frame.py` の draw_background の注記）。
            target.blit(self._background, (0, 0))
            target.blit(
                board.layer(world.board),
                (board.left + offset[0], board.top + offset[1]),
                special_flags=pygame.BLEND_PREMULTIPLIED,
            )
        for item in world.items:
            art.items.draw(target, item, now, offset)
        for bomb in world.bombs:
            art.bombs.draw(target, bomb, now, offset)
        for blast in world.blasts:
            art.blasts.draw(target, blast, rng, offset)
        alpha = 1.0
        on_board = [p for p in world.players if is_alive(p)]
        for player in sorted(on_board, key=lambda p: p.position.y):
            look = player_look(world, player, visuals.motion(player.id))
            alpha = art.players.draw(target, look, now, rng, offset, alpha)
        # 盤面の物は、炎を全部描いてから粘膜爆弾を描く（原型の draw の順）ので、
        # 輪を2つに分ける。種類を足すと、どちらの `match` も型検査で失敗する。
        # 描くかどうかと、どの輪で描くかを決めてから、扱いを書く。
        for actor in world.actors:
            match actor:
                case Foxfire():
                    fire = FoxfireLook(actor.cell, visuals.trail(actor, now))
                    art.foxfires.draw(target, fire, now, offset, alpha)
                case SlimeBomb():
                    pass  # 次の輪で描く
                case Pit() | Scatter() | BurntTongue():
                    # 原型の draw も描かない（落とし穴は見えないのが技の要点。撒く本体と
                    # 焼けた舌は、盤面に姿を持たない）。
                    pass
                case _:
                    assert_never(actor)
        for actor in world.actors:
            match actor:
                case SlimeBomb():
                    origin, hopped = visuals.slime(actor)
                    slime = slime_look(actor, origin, hopped)
                    art.slimes.draw(target, slime, now, offset)
                case Foxfire():
                    pass  # 前の輪で描いた
                case Pit() | Scatter() | BurntTongue():
                    pass  # 原型も描かない（前の輪の説明）
                case _:
                    assert_never(actor)
        for particle in visuals.particles:
            art.particles.draw(target, particle, offset)
        if self._band is not None:
            self._band.draw(target, world, match)


def background(layout: Layout) -> pygame.Surface:
    """描く面全体の背景（`art/frame.py` の draw_background）。

    背景は縦のグラデーションなので、どの列も同じ色の並びになる。幅 1px の列を描いて、
    横に引き伸ばす（描く面の全体を canvas で描くと、マス 60 で 100MB の配列を使う）。
    """
    width, height = layout.surface_size
    canvas = SurfaceCanvas(1, height)
    draw_background(canvas, layout)
    column = canvas.to_surface()
    surface = pygame.transform.scale(column, (width, height))
    if pygame.display.get_surface() is not None:
        return surface.convert()
    flat = pygame.Surface((width, height))
    flat.blit(surface, (0, 0))
    return flat
