"""描画の重さの測定で描く、いちばん重い場面（本物の描画の層 `Renderer` で描く）。

`tools/bench_render.py` から使う。延長戦で盤面がほぼ全部燃えている瞬間を想定し、試合の
状態（`WorldState`）と見た目だけの値（`BenchVisuals`）を作って、本物の `Renderer` に
描かせる。試合は進めない（測るのは描く重さだけ）。フレームの番号から、そのフレームの
状態と見た目の値を作り直す。

描くもの（数の出どころは `bench_render.py` の冒頭）：

- 盤面：壊せるブロックは置かない（燃え尽きた）。画面の揺れはいつも幅 10px（毎フレーム、
  見た目の乱数で ±5px ずらす。揺れている間は、背景と盤面を別々に貼る重いほうの道を通る）
- 爆風 297 件：位相をそろえる（1回の誘爆で全部が出た形。消え際の薄れた絵をまとめて
  貼るフレームがある）
- 粒子 105 個：四角い粒だけの行（ブロックの破片・煙・土ぼこりの色）と、光の玉だけの行
  （追いかける炎の通った跡 105 マス）を両方測る。どちらの行にも、回りながら浮かぶ顔を
  4 つ足す（倒れたプレイヤーごとに1つ）
- プレイヤー 4 体（4匹とも違う動物）：うさぎは歩きながら無敵の点滅、かえるは舌を伸ばし
  縮みさせ（戻るときはアイテムを掴む）、もぐらは掘る身ぶり、きつねは歩きながらとくぎの
  長押しのゲージを溜める。どれも状態の印を出す
- 爆弾 8 個・アイテム 20 個（うんこはいつも消える前の点滅）・粘膜爆弾 1 個（残り回数が
  少なく、赤い輪を出す）・追いかける炎 1 本
- 盤面の右の横の板（`panel/side_panel.py`）：時計は残り 30 秒より少なく、数字が
  毎フレーム明滅する。ゲーム速度のつまみ（1.5×）・名札 4 枚・キーの案内（人間2人と
  パッドの段）・ツールバー。きつねのとくぎの回数を 15 フレームごとに変え、名札の中身が
  変わるたびに板の絵を作り直す形（原型の 4 Hz）を測る。かえるともぐらは CPU（ゲージを
  描かないプレイヤーとして `Renderer` に渡す。2体とも長押しはしていない）

外周の鍋と飛んでいる葱は描かない（4体とも盤面にいる場面のほうが重い。理由は
`bench_render.py` の冒頭の「測っていないもの」）。

場面で使う絵は、作るときに全部描いておく（試合の前に描いておく `BakedArt.prebuild` と、
場面だけで出る状態の印の組み合わせ）。盤面は描く面の左上 (0, 0) に盤面の四角で切って
描き、横の板はその右に貼る（遊ぶときの窓の並び。`layout.WindowLayout`）。横の板の中身を
組む所と、盤面を描いて横の板を貼る所は、遊ぶときと同じ関数を呼ぶ
（`render/match_frame.py` の `panel_content`・`draw_match_frame`）。

遊ぶときに試合の画面へ重ねるもののうち、通知（`#toast`）・ポーズの幕・ラウンドの幕と
優勝の幕・確認の画面・通信対戦の案内の帯は、場面に入れていない。出ている間だけ重ね、
どれも取っておいた絵を1〜2枚貼るだけ（幕のぼかしは幕を出したときに1回だけ作る）。
"""

import math
import random
import time

import pygame

from animal_bomber.ai.levels import CpuLevelKey
from animal_bomber.domain.core.coord import Cell, Direction, Point
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.rules.match import MatchConfig
from animal_bomber.domain.rules.tuning import BLAST_DURATION, BOMB_FUSE, COLS, ROWS
from animal_bomber.domain.state.actions import Dig, Tongue
from animal_bomber.domain.state.actors import Foxfire, SlimeBomb
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.bomb import Blast, Bomb
from animal_bomber.domain.state.effects import EffectBag, EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.domain.state.match import MatchState
from animal_bomber.domain.state.player import PlayerId
from animal_bomber.domain.state.world import WorldState, create_world
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.hud.roster import Cpu, Human, Roster
from animal_bomber.presentation.hud.scoreboard import HudSource
from animal_bomber.presentation.render.art.player import BLINK_ALPHA
from animal_bomber.presentation.render.art.player_marks import MAX_MARKS
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.layout import PANEL_GAP, Layout
from animal_bomber.presentation.render.match_frame import (
    draw_match_frame,
    panel_content,
)
from animal_bomber.presentation.render.panel.side_panel import (
    PanelContent,
    SidePanel,
)
from animal_bomber.presentation.render.renderer import Renderer
from animal_bomber.presentation.render.ui.typeset import TextPainter
from animal_bomber.presentation.render.views.player import TrackedMotion, player_look
from bench_match_visuals import (
    CAST,
    SPINNER_FACE,
    SQUARE_COLORS,
    WALK_SPEED,
    BenchVisuals,
    MatchSceneSpec,
    open_cells,
)

CPU_PLAYERS: tuple[PlayerId, ...] = (1, 2)
"""CPU が操作するプレイヤー（かえるともぐら）。"""

ROSTER: Roster = (
    Human("1P"),
    Cpu(1, CpuLevelKey.NORMAL),
    Cpu(2, CpuLevelKey.ONI),
    Human("2P"),
)
"""名札とキーの案内に使う、誰が操作しているかの一覧（人間2人・CPU 2体）。"""

TIME_LEFT_TICKS = 25 * 60
"""時計の残り（tick）。30 秒より少なく、時計の数字が明滅する。"""

GAME_SPEED = 1.5
"""つまみの値（1 より大きく、つまみの箱の縁が黄色になる）。"""

SPECIAL_EVERY = 15
"""きつねのとくぎの回数を変える間隔（フレーム。原型の名札の作り直しの約 4 Hz）。"""

FRAME_MS = 1000 / 60
"""1 フレームの実時間（ms）。横の板の作り直しの間隔と明滅は、この時刻で数える。"""


class MatchScene:
    """1 フレームずつ描ける場面。作る前に `pygame.display.set_mode` を済ませておく。"""

    def __init__(self, spec: MatchSceneSpec, rng: random.Random) -> None:
        self._spec = spec
        layout = Layout(spec.tile)
        self._art = BakedArt(layout)
        self._renderer = Renderer(self._art, CosmeticRng(rng), cpu_players=CPU_PLAYERS)
        self._panel = SidePanel(TextPainter())
        self._panel_left = layout.board_size[0] + PANEL_GAP
        self._board_rect = pygame.Rect((0, 0), layout.board_size)
        self._cells = open_cells()
        self._world = self._build_world(rng)
        self._match = MatchState()
        self._config = MatchConfig(seed=1, animals=CAST[: spec.players], wins_to_take=3)
        self._fire = next(a for a in self._world.actors if isinstance(a, Foxfire))
        self._slime = next(a for a in self._world.actors if isinstance(a, SlimeBomb))
        self.visuals = BenchVisuals(spec, rng)
        started = time.perf_counter()
        self._art.prebuild(CAST[: spec.players])
        # 状態の印の組み合わせは、出たときに描く（`BakedArt.prebuild`）。場面では
        # どのフレームも同じ組み合わせなので、測る前に描いておく。
        self._pose(0)
        for player in self._world.players:
            look = player_look(self._world, player, TrackedMotion())
            for alpha in (1.0, BLINK_ALPHA):
                self._art.players.marks("".join(look.marks[:MAX_MARKS]), alpha)
        # 粒子の絵も出たときに描く（試合では、粒子の色と大きさは出るたびに違う）。
        # 場面の粒子の色と大きさ（3〜9px を 0.5px ごと）の全部を、測る前に描いておく。
        for color in SQUARE_COLORS:
            for side in range(6, 19):
                self._art.particles.square(color, side)
        self._art.particles.text(SPINNER_FACE, 26)
        # 横の板の名札は、とくぎの回数の3通りを描いておく（試合では、新しい文を初めて
        # 描くフレームが出るが、場面ではその分は測らない）。描いておくのに使った時刻の
        # あとから、測る時刻を数える（板の作り直しの間隔を、測る最初から守らせる）。
        scratch = pygame.Surface(spec.size)
        for frame in range(0, 3 * SPECIAL_EVERY, SPECIAL_EVERY):
            self._pose(frame)
            self._panel.show(self._panel_content(), frame * FRAME_MS)
            self._panel.draw(scratch, (self._panel_left, 0), frame * FRAME_MS)
        self._start_ms = 3 * SPECIAL_EVERY * FRAME_MS
        self._panel_builds_before = self._panel.builds
        self.prebuild_ms = (time.perf_counter() - started) * 1000

    @property
    def counts(self) -> dict[str, int]:
        """場面が持っている、描くものの数。"""
        spec = self._spec
        glow = spec.particle_kind == "glow"
        return {
            "blasts": len(self._world.blasts),
            "particles": spec.particles,
            "trail": spec.particles if glow else 3,
            "spinners": spec.spinners,
            "players": len(self._world.players),
            "bombs": len(self._world.bombs),
            "items": len(self._world.items),
        }

    @property
    def blast_phases(self) -> int:
        """爆風の位相の種類の数（そろえているので 1）。"""
        return len({blast.remaining for blast in self._world.blasts})

    @property
    def cached_sprites(self) -> int:
        """取っておいた絵の数（先に描いた分を含む）。"""
        return len(self._art.cache)

    @property
    def renders(self) -> int:
        """場面を作ってから描いた絵の数（測る間に増えたら、先に描き損ねた絵がある）。"""
        return self._art.cache.renders

    @property
    def panel_builds(self) -> int:
        """場面を作ってから、横の板の絵を作り直した回数（先に描いた分は数えない）。"""
        return self._panel.builds - self._panel_builds_before

    def draw(self, target: pygame.Surface, frame: int) -> None:
        """`frame` フレーム目を描く（盤面を左上に、横の板をその右に）。

        盤面を切って描いて横の板を貼る所は、遊ぶときと同じ関数
        （`render/match_frame.py` の `draw_match_frame`）を呼ぶ。
        """
        self._pose(frame)
        self.visuals.advance(frame, self._fire, self._cells)
        now_ms = self._start_ms + frame * FRAME_MS
        draw_match_frame(
            target,
            board_rect=self._board_rect,
            renderer=self._renderer,
            world=self._world,
            visuals=self.visuals,
            panel=self._panel,
            content=self._panel_content(),
            panel_topleft=(self._panel_left, 0),
            now_ms=now_ms,
        )

    def _panel_content(self) -> PanelContent:
        """いまの盤面から作る、横の板の中身（遊ぶときと同じ関数で組む）。"""
        source = HudSource(self._world, self._match, self._config, ROSTER, False)
        return panel_content(
            source,
            speed=GAME_SPEED,
            paused=False,
            can_pause=True,
            pad_connected=True,
            pad_in_match=True,
        )

    def _build_world(self, rng: random.Random) -> WorldState:
        spec = self._spec
        world = create_world(1, CAST[: spec.players])
        for cell, tile in list(world.board.cells()):
            if tile is Tile.SOFT:
                world.board.put(cell, Tile.EMPTY)
        cells = self._cells
        world.blasts = [
            Blast(EntityId(i), cells[i % len(cells)], 0, False, BLAST_DURATION)
            for i in range(spec.blasts)
        ]
        kinds = list(ItemKind)
        world.items = [
            Item(EntityId(1000 + i), rng.choice(cells), kinds[i % len(kinds)])
            for i in range(spec.items)
        ]
        world.bombs = [
            Bomb(EntityId(2000 + i), rng.choice(cells), 0, 1, BOMB_FUSE)
            for i in range(spec.bombs)
        ]
        world.actors = [
            Foxfire(cell=Cell(3, 7), owner=3),
            SlimeBomb(Cell(9, 9), 2, hops_left=2, flown=Tick(21), interval=Tick(24)),
        ]
        corners = [(1.5, 1.5), (COLS - 1.5, 1.5), (1.5, ROWS - 1.5), (COLS - 1.5, 9.5)]
        facings = [Direction.RIGHT, Direction.DOWN, Direction.UP, Direction.LEFT]
        for player, (x, y), facing in zip(
            world.players, corners, facings, strict=False
        ):
            player.position = Point(x, y)
            player.facing = facing
            player.has_special = True
            player.special_charges = 1
        return world

    def _pose(self, frame: int) -> None:
        """フレームの番号から、そのフレームの試合の状態にする（試合は進めない）。"""
        world = self._world
        now = Tick(frame)
        world.now = now
        world.ends_at = Tick(TIME_LEFT_TICKS)
        for blast in world.blasts:
            blast.remaining = Tick(BLAST_DURATION - frame % BLAST_DURATION)
        for index, bomb in enumerate(world.bombs):
            bomb.fuse = Tick(BOMB_FUSE - (frame + index * 17) % BOMB_FUSE)
        for item in world.items:
            if item.kind is ItemKind.POOP:
                item.expires_at = Tick(frame + 100)
        self._fire.cell = Cell(3 + (frame // 10) % 15, 7)
        self._slime.timer = Tick(24 - frame % 24)
        players = world.players
        swing = math.sin(frame * WALK_SPEED * 0.8) * 0.5
        if len(players) > 0:
            rabbit = players[0]
            rabbit.position = Point(1.5 + swing, 1.5)
            rabbit.invulnerable_until = Tick(frame + 75 - frame % 75)
            rabbit.effects = _effects(EffectKind.STUN)
        if len(players) > 1:
            phase = frame % 160
            returning = phase >= 80
            steps = (phase % 80) // 8
            players[1].action = Tongue(
                Cell(COLS - 2, 1),
                Direction.DOWN,
                Tick(phase % 80),
                steps=steps,
                length=10 - steps if returning else steps,
                returning=returning,
                caught=ItemKind.FIRE if returning else None,
            )
        if len(players) > 2:
            players[2].action = Dig(Cell(1, ROWS - 2), Tick(90 - frame % 91))
        if len(players) > 3:
            fox = players[3]
            fox.position = Point(COLS - 1.5 - swing, 9.5)
            fox.effects = _effects(EffectKind.REVERSE, EffectKind.NOBOMB)
            fox.action_held = Tick(1 + frame % 29)
            fox.action_fired = False
            # 名札の「🦊狐火×n」だけが変わる（盤面の絵は、回数でなく持っている印で
            # 描く）。
            fox.special_charges = 2 + (frame // SPECIAL_EVERY) % 3


def _effects(*kinds: EffectKind) -> EffectBag:
    """`kinds` がかかっている入れ物（残りは長くしておく）。"""
    bag = EffectBag()
    for kind in kinds:
        bag.set(kind, Tick(600))
    return bag
