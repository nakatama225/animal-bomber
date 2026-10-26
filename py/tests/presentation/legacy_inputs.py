"""原型の命令の列の固定値（`legacy_art_ops.json`）の入力から、描く関数の入力を作る。

固定値の入力は、原型の項目の名前と秒の値で書き出してある（`legacy_art.js`）。この版の
描く関数の入力のうち tick で持つもの（状態の残りなど）は、tick の数に直して渡す
（割り切れない値は止める）。粘膜爆弾・炎・粒子の入力は、原型と同じ秒の値で持つ。
"""

from typing import Any

from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import TICKS_PER_SECOND, Tick
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.rules.items import POOP_LIFETIME, ItemKind
from animal_bomber.domain.rules.lane import lane_spot
from animal_bomber.domain.rules.tuning import COLS, ROWS
from animal_bomber.domain.state.board import Board, Tile
from animal_bomber.domain.state.bomb import Blast, Bomb
from animal_bomber.domain.state.effects import EffectKind
from animal_bomber.domain.state.item import Item
from animal_bomber.presentation.render.art.animals.body import BodyPose
from animal_bomber.presentation.render.art.animals.frog import TongueLook
from animal_bomber.presentation.render.art.foxfires import FoxfireLook, TrailMark
from animal_bomber.presentation.render.art.frame import FrameScene
from animal_bomber.presentation.render.art.negibons import LeekLook, NegibonLook
from animal_bomber.presentation.render.art.particles import ParticleLook
from animal_bomber.presentation.render.art.player import PlayerLook
from animal_bomber.presentation.render.art.slimes import SlimeLook

DIRECTIONS = {
    "up": Direction.UP,
    "down": Direction.DOWN,
    "left": Direction.LEFT,
    "right": Direction.RIGHT,
}
"""原型の向きの名前と、この版の向き。"""

EFFECTS = {
    "slide": EffectKind.SLIDE,
    "stun": EffectKind.STUN,
    "reverse": EffectKind.REVERSE,
    "nobomb": EffectKind.NOBOMB,
    "runaway": EffectKind.RUNAWAY,
    "weak": EffectKind.WEAK,
    "autobomb": EffectKind.AUTOBOMB,
    "slow": EffectKind.SLOW,
    "pitfall": EffectKind.PITFALL,
    "foxLeap": EffectKind.LEAP,
    "poro": EffectKind.SCATTERING,
}
"""原型の effects の項目の名前と、この版の状態の種類。"""


SCATTERED_LIFETIME = Tick(3600)
"""とくぎで撒かれたうんこが消えるまで（原型の PORO_LIFE 60 秒）。"""


def item_from(inputs: dict[str, Any]) -> Item:
    """固定値のアイテムのケースの入力から、同じ時刻の関係を持つアイテムを作る。

    原型の born（置いた秒）は、この版では消える時刻（置いた tick ＋ 消えるまでの
    長さ）に、melt（溶けきるまでの残りの秒）は溶けきる時刻（いまの tick ＋ 残りの
    tick）にする。
    """
    raw = inputs["item"]
    kind = ItemKind(raw["kind"])
    scattered = bool(raw.get("poro"))
    expires_at = None
    if kind is ItemKind.POOP:
        lifetime = SCATTERED_LIFETIME if scattered else POOP_LIFETIME
        expires_at = Tick(raw["bornTicks"] + lifetime)
    melting_until = None
    if "meltTicks" in raw:
        melting_until = Tick(inputs["elapsedTicks"] + raw["meltTicks"])
    return Item(
        id=EntityId(1),
        cell=Cell(raw["x"], raw["y"]),
        kind=kind,
        scattered_by=0 if scattered else None,
        expires_at=expires_at,
        melting_until=melting_until,
    )


def ticks_of(value: float) -> Tick:
    """原型の秒の値を tick の数にする（固定値の秒の値は、tick で割り切れる）。"""
    ticks = round(value * TICKS_PER_SECOND)
    assert abs(value * TICKS_PER_SECOND - ticks) < 1e-9, (
        f"tick で割り切れない秒: {value}"
    )
    return Tick(ticks)


def player_look_from(raw: dict[str, Any]) -> PlayerLook:
    """固定値のプレイヤーの項目（原型の名前と秒の値）から、描く関数の入力を作る。"""
    effects: dict[str, float] = raw["effects"]
    last = raw["lastMoveAt"]
    if raw["chicken"] is not None:
        # 原型はチキンを拾うと、自分の動物のとくぎを持つ（chicken = animal.key）。
        assert raw["chicken"] == raw["animal"]
    pose = BodyPose(
        animal=Animal(raw["animal"]),
        facing=DIRECTIONS[raw["dir"]],
        walked=raw["walk"],
        # 原型の `p.lastMoveAt||-9` の -9 は「動いていない」。
        last_moved_at=None if last == -9 else ticks_of(last),
        scatter_left=ticks_of(effects.get("poro", 0)),
        leap_left=ticks_of(effects.get("foxLeap", 0)),
    )
    tongue = None
    if raw["tongue"] is not None:
        t = raw["tongue"]
        [direction] = [d for d in Direction if d.delta == (t["dx"], t["dy"])]
        tongue = TongueLook(
            direction=direction,
            length=t["len"],
            returning=t["phase"] != "out",
            since_step=t["t"],
            caught=None if t["item"] is None else ItemKind(t["item"]),
        )
    return PlayerLook(
        pose=pose,
        x=raw["cx"],
        y=raw["cy"],
        invulnerable=ticks_of(raw["invuln"]),
        hurt_shake=ticks_of(raw["hurtFlash"]),
        # 1枚の絵のケースは、足元のマスを書き出していない（どのプレイヤーも床の上）。
        in_block=raw.get("tileUnder", 0) != 0,
        pitfall=ticks_of(effects.get("pitfall", 0)),
        effects=tuple(EFFECTS[name] for name in effects),
        special=raw["chicken"] is not None,
        held=ticks_of(raw["actHold"]),
        fired=raw["actFired"],
        tongue=tongue,
        digging=None if raw["digging"] is None else ticks_of(raw["digging"]["t"]),
    )


def slime_look_from(raw: dict[str, Any]) -> SlimeLook:
    """固定値の粘膜爆弾の項目（原型の名前と秒の値）から、描く関数の入力を作る。"""
    return SlimeLook(
        cell=Cell(raw["x"], raw["y"]),
        origin=(raw["sx"], raw["sy"]),
        flying=raw["phase"] == "fly",
        flight=raw["t"],
        squash=raw["squash"],
        wobble=raw["wob"],
        hops_left=raw["hopsLeft"],
    )


def foxfire_look_from(raw: dict[str, Any]) -> FoxfireLook:
    """固定値の炎の項目（原型の名前）から、描く関数の入力を作る。"""
    trail = tuple(
        TrailMark(Cell(mark["x"], mark["y"]), mark["a"]) for mark in raw["trail"]
    )
    return FoxfireLook(Cell(raw["x"], raw["y"]), trail)


def particle_look_from(raw: dict[str, Any]) -> ParticleLook:
    """固定値の粒子の項目（原型の名前）から、描く関数の入力を作る。"""
    return ParticleLook(
        x=raw["x"],
        y=raw["y"],
        life=raw["life"],
        color=raw["col"],
        size=raw["sz"],
        text=raw.get("txt"),
        spin=raw.get("spin", False),
    )


def negibon_look_from(raw: dict[str, Any]) -> NegibonLook:
    """固定値の外周のプレイヤーの項目（原型の名前と秒の値）から、鍋の入力を作る。

    位置と撃つ向きは、この版の外周の式（`lane_spot`）で外周の位置（negiT）から出す。
    原型の negiPos の答え（`pos`）とは、向きが同じことをここで、位置が同じことを命令の
    列の比べで確認する。
    """
    spot = lane_spot(raw["negiT"])
    assert spot.facing is DIRECTIONS[raw["pos"]["dir"]]
    return NegibonLook(
        animal=Animal(raw["animal"]),
        x=spot.position.x,
        y=spot.position.y,
        facing=spot.facing,
        cooldown=ticks_of(raw["negiCool"]),
    )


def leek_look_from(raw: dict[str, Any]) -> LeekLook:
    """固定値の葱の項目（原型の x・y・vx・vy）から、葱の入力を作る。"""
    [facing] = [d for d in Direction if d.delta == (raw["vx"], raw["vy"])]
    return LeekLook(x=raw["x"], y=raw["y"], facing=facing)


def oracle_board() -> Board:
    """1枚の絵のケースの盤面（`legacy_art.js` の emptyGrid に、壊せるブロックを足す）。

    外周と、列も行も偶数のマスが壁。壊せるブロックは (3, 1) と (7, 5) の2つ。
    """
    tiles = []
    for row in range(ROWS):
        for col in range(COLS):
            border = col in (0, COLS - 1) or row in (0, ROWS - 1)
            pillar = col % 2 == 0 and row % 2 == 0
            tiles.append(Tile.HARD if border or pillar else Tile.EMPTY)
    board = Board(COLS, ROWS, tiles)
    board.put(Cell(3, 1), Tile.SOFT)
    board.put(Cell(7, 5), Tile.SOFT)
    return board


def frame_scene_from(inputs: dict[str, Any]) -> FrameScene:
    """1枚の絵のケースの入力から、1枚の絵に描くものを作る。

    盤面・アイテム・爆弾・爆風は、固定値の入力に書き出していないので、`legacy_art.js`
    の draw のケースに書いた値を写す（アイテムは火力・爆弾は導火線の残り 1 秒・爆風は
    残り 18 tick の真ん中の1マス）。粒子は、書き出してあればそれを、無ければ同じく
    写す（四角い粒1つ）。炎・粘膜爆弾・外周の鍋・葱は、書き出してあるケースだけにある。
    プレイヤーは盤面にいる者（state が ALIVE）だけを渡す（原型の drawPlayer は、盤面に
    いないプレイヤーでは最初に帰る）。
    """
    players = [
        player_look_from(raw) for raw in inputs["players"] if raw["state"] == "ALIVE"
    ]
    particles = [ParticleLook(4.3, 6.1, 0.4, "#ffd23f", 5)]
    if "particles" in inputs:
        particles = [particle_look_from(raw) for raw in inputs["particles"]]
    return FrameScene(
        board=oracle_board(),
        items=[Item(EntityId(1), Cell(4, 3), ItemKind.FIRE)],
        bombs=[Bomb(EntityId(2), Cell(5, 5), 0, 1, Tick(60))],
        blasts=[Blast(EntityId(3), Cell(6, 5), 0, True, Tick(18))],
        players=players,
        now=Tick(inputs["elapsedTicks"]),
        foxfires=[foxfire_look_from(raw) for raw in inputs.get("foxfires", [])],
        slimes=[slime_look_from(raw) for raw in inputs.get("slimes", [])],
        negibons=[negibon_look_from(raw) for raw in inputs.get("negibons", [])],
        leeks=[leek_look_from(raw) for raw in inputs.get("negis", [])],
        particles=particles,
        shake=inputs["shake"],
    )
