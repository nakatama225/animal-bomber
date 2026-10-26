"""1フレームの絵を、取っておいた絵を貼って描く（原型の draw）。

並べる順・画面の揺れ・見た目の乱数を取り出す順は、手本の `art/frame.py` の draw_frame と
同じ（背景 → 画面の揺れ → 床と壁 → アイテム → 爆弾 → 爆風 → プレイヤー（上にいる順）→
炎 → 粘膜爆弾 → 外周の鍋（プレイヤーの番号の順）→ 飛んでいる葱 → 粒子）。描く関数を
直接呼ぶ手本と違い、ここは取っておいた絵（`render/baked/`）を貼る。描くのは盤面だけで、
横の板と幕は `app/match_view.py` の `MatchView`（横の板は `render/match_frame.py` の
`draw_match_frame`）が、通知は `app/shell.py` が、同じ面の外の場所に貼る。

試合の状態（`WorldState`）は読むだけで書き換えない。試合の状態に無い値
（粒子・画面の揺れ・歩いた距離など）は `Visuals` から読む（`scene/tracker.py` の
`SceneTracker` が数える）。

## 画面の揺れ

原型と同じく、揺れが 0.2 を超えていれば、描くたびに見た目の乱数を横・縦の順に2つ
取り出してずらす（決着のあとの待ちの間も、止まった揺れの幅のまま揺らす）。ずれは整数の
px に丸めて貼る（丸めのずれは 0.5px まで。取っておいた絵はマスの左上からの小数のずれが
同じ所に貼るので、整数でずらせば絵は変わらない。`shake_shift`）。使ったずれは
`Renderer.shaken` に残す（原型のポーズの幕は揺れた canvas の中に描くので、同じずれで
重ねる。`app/match_view.py`）。

## 落とし穴の、不透明度の戻し忘れ

原型の drawPlayer は、落とし穴にはまったプレイヤーを描くと、不透明度を戻さずに帰る
（`art/player.py` の draw_player の注記）。そのフレームのそのあとに描くもののうち、
不透明度を自分で決めないもの（あとに描くプレイヤーとその舌・掘る身ぶり、炎の火の玉、
飛んでいる葱）は、その不透明度で描かれる。外周の鍋は不透明度を自分で 0.95 にするので
受けない。手本の draw_frame は命令どおりに写してあるので、ここも同じく、プレイヤーを
貼るたびに返る不透明度を、次のプレイヤーと炎と葱へ渡す。

⚠️ 原型では、落とし穴にはまったプレイヤーが同じフレームに2体いて、先に描くほうが点滅して
いると、フレームを描き終えたあとも canvas の不透明度が戻らず、次のフレームからは背景や
床まで薄く描かれる（前のフレームの絵が透けて残る）。この版はフレームごとに描き直すので、
フレームをまたいでは写さない（docs/08 の「原型と違うまま残した所」）。
"""

from collections.abc import Collection, Sequence
from typing import Protocol, assert_never

import pygame

from animal_bomber.domain.core.coord import Point
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.state.actors import (
    BurntTongue,
    Foxfire,
    Leek,
    Pit,
    Scatter,
    SlimeBomb,
)
from animal_bomber.domain.state.player import (
    Alive,
    Negibon,
    Out,
    PlayerId,
    is_alive,
)
from animal_bomber.domain.state.world import WorldState
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.render.art.foxfires import FoxfireLook, TrailMark
from animal_bomber.presentation.render.art.frame import draw_background, shake_offset
from animal_bomber.presentation.render.art.particles import ParticleLook
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.baked.board import BoardLayer
from animal_bomber.presentation.render.baked.techniques import snap
from animal_bomber.presentation.render.canvas.surface import SurfaceCanvas
from animal_bomber.presentation.render.layout import Layout
from animal_bomber.presentation.render.views.actors import (
    drawn_flown,
    leek_look,
    slime_look,
)
from animal_bomber.presentation.render.views.lane import negibon_look
from animal_bomber.presentation.render.views.particles import drawn_particle
from animal_bomber.presentation.render.views.player import (
    TrackedMotion,
    drawn_time,
    player_look,
)


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

    def flown_before(self, actor: SlimeBomb) -> Tick | None:
        """粘膜爆弾の、1つ前の tick の終わりの投げてからの tick（無ければ None）。"""
        ...

    def leek_before(self, actor: Leek) -> Point | None:
        """飛んでいる葱の、1つ前の tick の終わりの位置（無ければ None）。"""
        ...

    def trail(self, actor: Foxfire, now: float) -> tuple[TrailMark, ...]:
        """炎の通った跡。濃さは描く時刻 `now` のもの。"""
        ...


class Renderer:
    """1フレームの絵を描く。

    `art` は試合の前に描いておいた絵（`BakedArt.prebuild`）、`rng` は見た目の乱数
    （画面の揺れ・爆風のちらつき・被弾の揺れ）。

    `cpu_players` は CPU が操作しているプレイヤーの番号。そのプレイヤーには、とくぎの
    長押しのゲージを描かない（原型の CPU は長押しの長さを増やさない。`art/player.py`
    の `gauge_progress`）。省くと空（全員を人間として描く）。試合ごと、と、試合の途中で
    替わったとき（通信対戦で抜けたプレイヤーを CPU が引き継いだ）は、属性に入れ直す。
    """

    def __init__(
        self,
        art: BakedArt,
        rng: CosmeticRng | None = None,
        cpu_players: Collection[PlayerId] = (),
    ) -> None:
        self.art = art
        self.cpu_players: frozenset[PlayerId] = frozenset(cpu_players)
        """CPU が操作しているプレイヤーの番号（クラスの説明）。"""
        self.shaken: tuple[int, int] = (0, 0)
        """最後に描いたフレームの、画面の揺れのずれ（px。揺らさなかったら (0, 0)）。"""
        self._rng = rng if rng is not None else CosmeticRng()
        layout = art.layout
        self._background = background(layout)
        self._board = BoardLayer(art.board, layout)

    @property
    def layout(self) -> Layout:
        """盤面を描く面の寸法。"""
        return self.art.layout

    @property
    def background(self) -> pygame.Surface:
        """盤面の背景（揺らさない縦のグラデーション。盤面の大きさ。書き換えない）。"""
        return self._background

    def draw(
        self,
        target: pygame.Surface,
        world: WorldState,
        visuals: Visuals,
        blend: float = 1.0,
        *,
        origin: tuple[int, int] = (0, 0),
    ) -> None:
        """いまの盤面を `target`（描く面。アルファの桁の無い面）の `origin` に描く。

        `origin` は盤面の左上を置く位置（px。既定は描く面の左上）。窓の面では、盤面の
        枠の太さだけ内側（`layout.WindowLayout.board_rect`）。背景・盤面・揺れでずらす
        絵を全部同じだけずらすので、`origin` を変えても、見た目の乱数を取り出す順と、
        盤面の中の絵は変わらない。

        `blend` は、描く値を1つ前の tick の値と混ぜる割合（既定の 1 はいまの値。ゲーム
        速度が整数でない1台の試合だけ 1 より小さい。`shell/loop.py` の
        `GameSpeed.blend`）。混ぜるのは、盤面にいるプレイヤーの位置と歩いた距離と
        舌先までの長さ（`views/player.py` の `drawn_position`・`player_look`）・外周の
        鍋の位置（`views/lane.py` の `drawn_along`）・飛んでいる葱の位置・粘膜爆弾の
        飛ぶ間（`views/actors.py`）・粒子（`views/particles.py`）と、時刻で決まる絵に
        渡す描く時刻（`views/player.py` の `drawn_time`）。残りの tick の数か期限で
        持つ値（爆弾の導火線・無敵・ゲージ・撃つ間隔）も描く時刻の値にする（爆弾には
        描く時刻が盤面の時刻より何 tick 前かを渡す）。炎の位置は混ぜない（原型も
        マス単位で動く）。重ねる順（上にいる順）も、描く位置で決める。

        ⚠️ 画面の揺れでずらした盤面と粒子は、盤面の大きさ（`Layout.surface_size`）の
        外へはみ出して描くことがある。窓の大きさの面に描くときは、呼ぶ側が盤面の四角で
        切っておく（`target.set_clip`。原型の canvas も盤面の外を描かない。盤面の枠は
        切り取りの外なので、揺れても動かない）。
        """
        art, rng, now = self.art, self._rng, world.now
        at = drawn_time(now, blend)
        behind = now - at
        shake = shake_shift(visuals.shake, rng)
        self.shaken = shake
        # 揺れのずれに盤面の左上の位置を足した、絵を貼るときのずれ。揺れているかは
        # 揺れのずれだけで決める（足したずれで決めると、`origin` が (0, 0) でないとき
        # 毎フレーム揺れているほうの道を通る）。
        offset = (origin[0] + shake[0], origin[1] + shake[1])
        board = self._board
        if shake == (0, 0):
            target.blit(board.still(world.board, self._background), origin)
        else:
            # 背景は揺らさない（`art/frame.py` の draw_background の注記）。
            target.blit(self._background, origin)
            target.blit(
                board.layer(world.board),
                (board.left + offset[0], board.top + offset[1]),
                special_flags=pygame.BLEND_PREMULTIPLIED,
            )
        for item in world.items:
            art.items.draw(target, item, at, offset)
        for bomb in world.bombs:
            art.bombs.draw(target, bomb, at, offset, behind)
        for blast in world.blasts:
            art.blasts.draw(target, blast, rng, offset)
        alpha = 1.0
        cpus = self.cpu_players
        looks = [
            player_look(
                world,
                player,
                visuals.motion(player.id),
                cpu=player.id in cpus,
                blend=blend,
            )
            for player in world.players
            if is_alive(player)
        ]
        for look in sorted(looks, key=lambda look: look.y):
            alpha = art.players.draw(target, look, at, rng, offset, alpha)
        # 盤面の物は、炎を全部描いてから粘膜爆弾を描く（原型の draw の順）ので、
        # 輪を2つに分ける。種類を足すと、どちらの `match` も型検査で失敗する。
        # 描くかどうかと、どの輪で描くかを決めてから、扱いを書く。
        for actor in world.actors:
            match actor:
                case Foxfire():
                    fire = FoxfireLook(actor.cell, visuals.trail(actor, at))
                    art.foxfires.draw(target, fire, at, offset, alpha)
                case SlimeBomb():
                    pass  # 次の輪で描く
                case Pit() | Scatter() | BurntTongue():
                    # 原型の draw も描かない（落とし穴は見えないのが技の要点。撒く本体と
                    # 焼けた舌は、盤面に姿を持たない）。
                    pass
                case Leek():
                    pass  # 外周の鍋のあとの輪で描く
                case _:
                    assert_never(actor)
        for actor in world.actors:
            match actor:
                case SlimeBomb():
                    thrown, hopped = visuals.slime(actor)
                    flown = drawn_flown(actor.flown, visuals.flown_before(actor), blend)
                    slime = slime_look(actor, thrown, hopped, flown)
                    art.slimes.draw(target, slime, at, offset)
                case Foxfire():
                    pass  # 前の輪で描いた
                case Pit() | Scatter() | BurntTongue():
                    pass  # 原型も描かない（前の輪の説明）
                case Leek():
                    pass  # 外周の鍋のあとの輪で描く
                case _:
                    assert_never(actor)
        # 外周の鍋を全員ぶん（プレイヤーの番号の順に）描いてから、飛んでいる葱を全部描く
        # （原型の drawNegibons）。鍋は不透明度を自分で決めるので `alpha` を受けず、葱は
        # 受ける（モジュールの説明の、落とし穴の戻し忘れ）。
        for player in world.players:
            life = player.life
            match life:
                case Negibon():
                    previous = visuals.motion(player.id).previous_along
                    lane = negibon_look(player, life, now, previous, blend)
                    art.negibons.draw(target, lane, offset)
                case Alive() | Out():
                    pass
                case _:
                    assert_never(life)
        for actor in world.actors:
            match actor:
                case Leek():
                    leek = leek_look(actor, visuals.leek_before(actor), blend)
                    art.negibons.draw_leek(target, leek, offset, alpha)
                case Foxfire() | SlimeBomb():
                    pass  # 前の輪で描いた
                case Pit() | Scatter() | BurntTongue():
                    pass  # 原型も描かない（最初の輪の説明）
                case _:
                    assert_never(actor)
        for particle in visuals.particles:
            art.particles.draw(target, drawn_particle(particle, blend), offset)


def shake_shift(shake: float, rng: CosmeticRng) -> tuple[int, int]:
    """画面の揺れの幅 `shake`（px）から、このフレームのずれ（整数の px）を決める。

    揺れが 0.2 を超えていれば、見た目の乱数を横・縦の順に2つ取り出し（`art/frame.py` の
    `shake_offset`）、いちばん近い整数の px に丸める（モジュールの説明の「画面の
    揺れ」）。揺れが小さければ乱数を取り出さずに (0, 0)。幕の間の盤面の揺れ
    （`app/match_view.py`）も、この関数で同じ乱数から取り出す。
    """
    moved = shake_offset(shake, rng)
    return (0, 0) if moved is None else (snap(moved[0]), snap(moved[1]))


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
