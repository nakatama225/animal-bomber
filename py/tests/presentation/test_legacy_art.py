"""描く関数が、原型と同じ canvas の命令の列を出すことの検査。

固定値（`legacy_art_ops.json`）は、原型（`legacy/animal-bomber.html`）を node で
読み込み、canvas を「呼ばれた命令と状態の代入を順に記録する偽物」に替えて、描く関数を
いろいろな入力（マス 44 と 60）で呼んで書き出したもの。`Math.random` は決めた値の列に
差し替え、引いた値も記録してある。リポジトリのいちばん上で次を走らせると作り直せる
（何度作っても同じものになる）。

    node py/tools/legacy_oracle/legacy_art.js py/tests/presentation/legacy_art_ops.json

原型の入力は秒だが、固定値の入力は tick の数で割り切れる値にしてあり、tick の数も
書き出してある（`elapsedTicks`・`fuseTicks`・`remainingTicks`・`bornTicks`・
`meltTicks` など）。この版の描く関数には tick の数から作った試合の状態を渡し、原型と
同じ列が出るかを見る。乱数を引くケースは、原型と同じ値の列を見た目の乱数に差し、同じ
順・同じ数だけ引くかも見る。

体・頭・尻尾・目・角の丸い四角は、原型では drawPlayer の中で呼ばれる。drawPlayer は
足元の影・色の輪・状態の印も描くので、固定値にはこれらの部品を直接呼んだケースも
入れてある（`legacy_art.js` の後半）。プレイヤー・粘膜爆弾・炎・粒子・1枚の絵の入力は、
原型の項目の名前で書き出してあるので、描く関数の入力の形に直してから渡す
（`legacy_inputs.py`）。

まだ写していない描く関数のケースは、名前を挙げて飛ばす（`NEXT_STAGE`）。いまは全部
写してあるので空。固定値に描く関数を足したら（葱ボンの段階 8 など）、写すまでここに
挙げる。
"""

from collections.abc import Callable
from typing import Any

import pytest

from animal_bomber.domain.core.coord import Cell
from animal_bomber.domain.core.entity_id import EntityId
from animal_bomber.domain.core.tick import Tick
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.state.board import Tile
from animal_bomber.domain.state.bomb import Blast, Bomb
from animal_bomber.presentation.cosmetic_rng import CosmeticRng, ScriptedRandom
from animal_bomber.presentation.render.art.animals.body import (
    BodyPose,
    draw_animal_body,
)
from animal_bomber.presentation.render.art.animals.eye import EyeOptions, draw_eye
from animal_bomber.presentation.render.art.animals.looks import TailKind
from animal_bomber.presentation.render.art.animals.rabbit import head_rabbit
from animal_bomber.presentation.render.art.animals.tail import draw_tail
from animal_bomber.presentation.render.art.blasts import draw_blast
from animal_bomber.presentation.render.art.board import draw_tile
from animal_bomber.presentation.render.art.bombs import draw_bomb
from animal_bomber.presentation.render.art.foxfires import draw_foxfire
from animal_bomber.presentation.render.art.frame import draw_frame
from animal_bomber.presentation.render.art.items import draw_item
from animal_bomber.presentation.render.art.particles import draw_particle
from animal_bomber.presentation.render.art.player import draw_player
from animal_bomber.presentation.render.art.shapes import ink_line, round_rect
from animal_bomber.presentation.render.art.slimes import draw_slime
from animal_bomber.presentation.render.canvas.recording import RecordingCanvas
from animal_bomber.presentation.render.layout import Layout

from .legacy_inputs import (
    DIRECTIONS,
    foxfire_look_from,
    frame_scene_from,
    item_from,
    particle_look_from,
    player_look_from,
    slime_look_from,
)
from .legacy_ops import FIXTURE, mismatch

NEXT_STAGE: frozenset[str] = frozenset()
"""まだ写していない描く関数（次の段で写す）。ここに挙げたケースは飛ばす。"""

_TILES = {"hard": Tile.HARD, "soft": Tile.SOFT, "empty": Tile.EMPTY}

Drawer = Callable[[RecordingCanvas, dict[str, Any], CosmeticRng], None]


def _draw_tile(canvas: RecordingCanvas, inputs: dict[str, Any], _: CosmeticRng) -> None:
    cell = Cell(inputs["x"], inputs["y"])
    draw_tile(canvas, Layout(inputs["tile"]), _TILES[inputs["tileKind"]], cell)


def _draw_item(canvas: RecordingCanvas, inputs: dict[str, Any], _: CosmeticRng) -> None:
    now = Tick(inputs["elapsedTicks"])
    draw_item(canvas, Layout(inputs["tile"]), item_from(inputs), now)


def _draw_bomb(canvas: RecordingCanvas, inputs: dict[str, Any], _: CosmeticRng) -> None:
    raw = inputs["bomb"]
    bomb = Bomb(
        id=EntityId(1),
        cell=Cell(raw["x"], raw["y"]),
        owner=0,
        power=1,
        fuse=Tick(raw["fuseTicks"]),
    )
    draw_bomb(canvas, Layout(inputs["tile"]), bomb, Tick(inputs["elapsedTicks"]))


def _draw_blast(
    canvas: RecordingCanvas, inputs: dict[str, Any], rng: CosmeticRng
) -> None:
    raw = inputs["blast"]
    blast = Blast(
        id=EntityId(1),
        cell=Cell(raw["x"], raw["y"]),
        owner=0,
        is_center=raw["center"],
        remaining=Tick(raw["remainingTicks"]),
    )
    draw_blast(canvas, Layout(inputs["tile"]), blast, rng)


def _round_rect(
    canvas: RecordingCanvas, inputs: dict[str, Any], _: CosmeticRng
) -> None:
    round_rect(canvas, inputs["x"], inputs["y"], inputs["w"], inputs["h"], inputs["r"])


def _draw_eye(canvas: RecordingCanvas, inputs: dict[str, Any], _: CosmeticRng) -> None:
    raw = inputs["opt"] or {}
    options = EyeOptions(
        closed=raw.get("closed", False),
        white=raw.get("white"),
        iris=raw.get("iris"),
        look=raw.get("look", 0),
        tall=raw.get("tall"),
    )
    draw_eye(
        canvas,
        inputs["x"],
        inputs["y"],
        inputs["r"],
        inputs["mode"],
        options if inputs["opt"] else None,
    )


def _draw_tail(canvas: RecordingCanvas, inputs: dict[str, Any], _: CosmeticRng) -> None:
    draw_tail(
        canvas,
        TailKind(inputs["kind"]),
        inputs["bodyW"],
        inputs["bodyH"],
        inputs["bodyCY"],
        inputs["side"],
        inputs["back"],
        inputs["col"],
        inputs["dark"],
        inputs["fur"],
        lambda width: ink_line(canvas, width),
        inputs["swing"],
    )


def _head_rabbit(
    canvas: RecordingCanvas, inputs: dict[str, Any], _: CosmeticRng
) -> None:
    head_rabbit(
        canvas,
        inputs["x"],
        inputs["y"],
        inputs["r"],
        inputs["mode"],
        inputs["col"],
        inputs["dark"],
        inputs["fur"],
    )


def _draw_body(canvas: RecordingCanvas, inputs: dict[str, Any], _: CosmeticRng) -> None:
    last = inputs["lastMoveTicks"]
    pose = BodyPose(
        animal=Animal(inputs["animal"]),
        facing=DIRECTIONS[inputs["dir"]],
        walked=inputs["walk"],
        last_moved_at=None if last is None else Tick(last),
        scatter_left=Tick(inputs["poroTicks"]),
        leap_left=Tick(inputs["leapTicks"]),
    )
    draw_animal_body(canvas, inputs["tile"], pose, Tick(inputs["elapsedTicks"]))


def _draw_player(
    canvas: RecordingCanvas, inputs: dict[str, Any], rng: CosmeticRng
) -> None:
    look = player_look_from(inputs["player"])
    draw_player(canvas, Layout(inputs["tile"]), look, Tick(inputs["elapsedTicks"]), rng)


def _draw_slime(
    canvas: RecordingCanvas, inputs: dict[str, Any], _: CosmeticRng
) -> None:
    look = slime_look_from(inputs["slime"])
    draw_slime(canvas, Layout(inputs["tile"]), look, Tick(inputs["elapsedTicks"]))


def _draw_foxfire(
    canvas: RecordingCanvas, inputs: dict[str, Any], _: CosmeticRng
) -> None:
    look = foxfire_look_from(inputs["foxfire"])
    draw_foxfire(canvas, Layout(inputs["tile"]), look, Tick(inputs["elapsedTicks"]))


def _draw_particle(
    canvas: RecordingCanvas, inputs: dict[str, Any], _: CosmeticRng
) -> None:
    look = particle_look_from(inputs["particle"])
    draw_particle(canvas, Layout(inputs["tile"]), look)


def _draw(canvas: RecordingCanvas, inputs: dict[str, Any], rng: CosmeticRng) -> None:
    draw_frame(canvas, Layout(inputs["tile"]), frame_scene_from(inputs), rng)


DRAWERS: dict[str, Drawer] = {
    "drawTile": _draw_tile,
    "drawItem": _draw_item,
    "drawBomb": _draw_bomb,
    "drawBlast": _draw_blast,
    "roundRect": _round_rect,
    "drawEye": _draw_eye,
    "drawTail": _draw_tail,
    "headRabbit": _head_rabbit,
    "drawAnimalBody": _draw_body,
    "drawPlayer": _draw_player,
    "drawSlimes": _draw_slime,
    "drawFoxfires": _draw_foxfire,
    "drawParticle": _draw_particle,
    "draw": _draw,
}
"""写した描く関数と、固定値の入力からそれを呼ぶ関数。"""

CASES: list[dict[str, Any]] = FIXTURE["cases"]


def _case_id(case: dict[str, Any]) -> str:
    return f"{case['fn']}/{case['name']}"


@pytest.mark.parametrize("case", CASES, ids=_case_id)
def test_原型と同じ命令の列を出す(case: dict[str, Any]) -> None:
    """写し間違い（式・定数・命令の順・状態の代入の抜け）を、原型の記録で見つける。"""
    if case["fn"] in NEXT_STAGE:
        pytest.skip(f"次の段で写す描く関数: {case['fn']}")
    scripted = ScriptedRandom(FIXTURE["randomValues"])
    canvas = RecordingCanvas()
    DRAWERS[case["fn"]](canvas, case["inputs"], CosmeticRng(scripted))
    problem = mismatch(canvas.ops, case["ops"])
    assert problem is None, problem
    assert scripted.used == case["random"], "見た目の乱数を引いた値と回数が原型と違う"


def test_固定値の描く関数は_写したものか次の段のものだけ() -> None:
    """固定値に描く関数を足したのに、どちらにも入れ忘れて黙って飛ばす事故を防ぐ。

    写した数と飛ばす数もここで決める（飛ばす数が増えたら、写すものが減っている）。
    """
    names = [case["fn"] for case in CASES]
    assert set(names) <= set(DRAWERS) | NEXT_STAGE
    assert not set(DRAWERS) & NEXT_STAGE
    checked = sum(1 for name in names if name in DRAWERS)
    skipped = sum(1 for name in names if name in NEXT_STAGE)
    assert (checked, skipped) == (242, 0)


def test_無敵の点滅の両方の向きを確かめている() -> None:
    """固定値に、点滅で薄くなっているケースと濃いケースの両方があること。

    floor(残り × 14) が偶数のとき薄くなる。初めは薄くなるはずのケースの残りが 0.7 秒
    （floor(9.8) = 9）で、薄くなる側を確かめていなかった。
    """
    blinking = [
        case["inputs"]["player"]["invuln"]
        for case in CASES
        if case["fn"] == "drawPlayer" and case["inputs"]["player"]["invuln"] > 0
    ]
    parity = {int(left * 14) % 2 for left in blinking}
    assert parity == {0, 1}


def test_記録する_canvas_は負の半径で例外を出す() -> None:
    """ブラウザは負の半径で例外を出す。写しも止めないと、壊れた値に気づけない。"""
    canvas = RecordingCanvas()
    with pytest.raises(ValueError, match="半径"):
        canvas.arc(0, 0, -1, 0, 7)
    with pytest.raises(ValueError, match="半径"):
        canvas.ellipse(0, 0, 1, -1, 0, 0, 7)
