"""粒子の出し方と動かし方（原型の puff・destroySoft・kill・hop と update の粒子の輪）。

出し方の式と、見た目の乱数を引く順は原型と同じにする。原型の粒子は object の項目を
書いた順に作るので、1つの粒子の中では x・y・vx・vy・life・sz の順に、式に乱数がある
ものだけ引く（固定値 `tests/presentation/legacy_particles.json` と突き合わせてある）。

位置と速さはマス、大きさは px（原型の sz）。動かし方は原型の update と同じで、
1 tick（1/60 秒）ごとに、寿命を減らし、位置を速さぶん進め、縦の速さに重力を足す。
寿命が 0 以下になったものを消す。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, assert_never

from animal_bomber.domain.core.coord import Cell, Direction
from animal_bomber.domain.core.tick import TICKS_PER_SECOND
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.presentation.cosmetic_rng import CosmeticRng
from animal_bomber.presentation.render.art.animals.looks import look_of
from animal_bomber.presentation.render.art.particles import ParticleLook

DT: Final = 1 / TICKS_PER_SECOND
"""1 tick の秒（原型の update の dt）。"""

GRAVITY: Final = 6.0
"""粒子にかかる下向きの加速（マス毎秒毎秒。原型の `vy += 6 * dt`）。"""

DEBRIS_COLOR: Final = "#a2703f"
"""ブロックの破片の色（原型の値）。"""

SPLASH_COLOR: Final = "#9fd8ff"
"""鼻水の水しぶきの色（原型の値）。"""

DUST_COLOR: Final = "#a6e06a"
"""跳んだときの土ぼこりの色（原型の値）。"""

SCOOP_COLOR: Final = "#ffd23f"
"""突進で吸い込んだアイテムの絵文字の粒子の色（原型の値。絵文字なので描く色には出ない）。"""

GOOD_SMOKE: Final = "#ffd23f"
"""良いアイテムを拾ったとき・吐き出したときの煙の色（原型の値）。"""

BAD_SMOKE: Final = "#b98a5a"
"""悪いアイテムを拾ったときの煙の色（原型の値）。"""

CARRIED_SMOKE: Final = "#c98a8a"
"""突進が抱えた・撒き散らした悪いアイテムの煙の色（原型の値）。"""

SCATTERED_SMOKE: Final = "#f7a8c4"
"""とくぎで撒いたうんこの煙の色（撒いたとき・消えたとき。原型の値）。"""

POOP_SMOKE: Final = "#8a6a3a"
"""ふつうのうんこが吹き飛んだ・消えたときの煙の色（原型の値）。"""

WATER_SMOKE: Final = "#9fd8ff"
"""鼻水で消した爆弾・溶けきったうんこの煙の色（原型の値）。"""

BURNED_SMOKE: Final = "#6b5443"
"""爆風で焼けたアイテムの煙の色（原型の値）。"""

PIT_SMOKE: Final = "#8a5a2a"
"""落とし穴に落ちたときの煙の色（原型の値）。"""

TONGUE_SMOKE: Final = "#ff7a5a"
"""焼き切れた舌の煙の色（原型の値）。"""

FOXFIRE_SMOKE: Final = "#8ce0ff"
"""炎が寿命で消えたときの煙の色（原型の値）。"""


@dataclass(frozen=True, slots=True)
class Particle:
    """粒子1つ（原型の particles の1つ）。"""

    x: float
    """位置の横（マス）。"""
    y: float
    """位置の縦（マス）。"""
    vx: float
    """横の速さ（マス毎秒）。"""
    vy: float
    """縦の速さ（マス毎秒。下が正）。"""
    life: float
    """寿命の残り（秒）。"""
    color: str
    """四角い粒の色（原型の col）。"""
    size: float
    """四角い粒の一辺、または絵文字の大きさ（px。原型の sz）。"""
    text: str | None = None
    """絵文字（原型の txt）。None なら四角い粒。"""
    spin: bool = False
    """絵文字を回しながら浮かべるか（原型の spin）。"""

    def look(self) -> ParticleLook:
        """描く関数の入力（`render/art/particles.py`）。"""
        return ParticleLook(
            self.x, self.y, self.life, self.color, self.size, self.text, self.spin
        )


def advanced(particles: Sequence[Particle]) -> list[Particle]:
    """1 tick 進めた粒子（原型の update の粒子の輪）。寿命の尽きたものは除く。

    並びは変えない（原型も後ろから見て消すだけなので、残ったものの順は変わらない）。
    縦の位置は、重力を足す前の縦の速さで進める（原型と同じ順）。
    """
    moved = []
    for p in particles:
        life = p.life - DT
        if life <= 0:
            continue
        moved.append(
            Particle(
                p.x + p.vx * DT,
                p.y + p.vy * DT,
                p.vx,
                p.vy + GRAVITY * DT,
                life,
                p.color,
                p.size,
                p.text,
                p.spin,
            )
        )
    return moved


def puff(cell: Cell, color: str, text: str, rng: CosmeticRng) -> list[Particle]:
    """煙（原型の puff）。マスの中央から、絵文字が1つ浮き上がり、四角い粒が6つ散る。

    見た目の乱数を 24 個引く（粒1つに4個）。
    """
    x, y = cell.col + 0.5, cell.row + 0.5
    out = [Particle(x, y, 0.0, -1.2, 0.6, color, 20, text)]
    for _ in range(6):
        vx = (rng.random() - 0.5) * 2.6
        vy = -rng.random() * 2.2
        life = 0.4 + rng.random() * 0.3
        size = 3 + rng.random() * 3
        out.append(Particle(x, y, vx, vy, life, color, size))
    return out


def debris(cell: Cell, rng: CosmeticRng) -> list[Particle]:
    """壊れたブロックの破片（原型の destroySoft）。7 つ。見た目の乱数を 42 個引く。

    原型はこのあとアイテムの抽選に乱数を引くが、それはルールの層の乱数（`roll_drop`）。
    """
    out = []
    for _ in range(7):
        x = cell.col + 0.5 + (rng.random() - 0.5) * 0.6
        y = cell.row + 0.5 + (rng.random() - 0.5) * 0.6
        vx = (rng.random() - 0.5) * 2.4
        vy = -rng.random() * 2.4 - 0.5
        life = 0.5 + rng.random() * 0.3
        size = 4 + rng.random() * 4
        out.append(Particle(x, y, vx, vy, life, DEBRIS_COLOR, size))
    return out


def knocked_out(x: float, y: float, animal: Animal, rng: CosmeticRng) -> list[Particle]:
    """倒れたとき（原型の kill）。体の色の粒 16 個と、回りながら浮かぶ動物の顔 1 つ。

    (x, y) は倒れたプレイヤーの位置（マス）。見た目の乱数を 64 個引く。
    """
    color = look_of(animal).color
    out = []
    for _ in range(16):
        vx = (rng.random() - 0.5) * 4
        vy = -rng.random() * 3.6 - 0.6
        life = 0.7 + rng.random() * 0.5
        size = 4 + rng.random() * 5
        out.append(Particle(x, y, vx, vy, life, color, size))
    face = animal_emoji(animal)
    out.append(Particle(x, y - 0.2, 0.0, -0.7, 1.1, "#fff", 26, face, True))
    return out


def scooped(cell: Cell, text: str, rng: CosmeticRng) -> list[Particle]:
    """突進で吸い込んだ良いアイテム（原型の chargeSweep）。絵文字が上へ舞う 3 つ。

    見た目の乱数を 9 個引く。
    """
    out = []
    for _ in range(3):
        x = cell.col + 0.5 + (rng.random() - 0.5) * 0.3
        vx = (rng.random() - 0.5) * 1.2
        vy = -3.4 - rng.random() * 1.2
        out.append(Particle(x, cell.row + 0.45, vx, vy, 0.5, SCOOP_COLOR, 20, text))
    return out


def splash(cell: Cell, facing: Direction, rng: CosmeticRng) -> list[Particle]:
    """鼻水の水しぶき（原型の elephantSnot）。届いたマス1つにつき 4 つ。

    吹いた向きへ飛ぶ。見た目の乱数を 20 個引く。
    """
    dx, dy = facing.delta
    out = []
    for _ in range(4):
        x = cell.col + 0.5 + (rng.random() - 0.5) * 0.5
        y = cell.row + 0.5 + (rng.random() - 0.5) * 0.5
        vx = dx * 3 + (rng.random() - 0.5) * 1.6
        vy = dy * 3 + (rng.random() - 0.5) * 1.6
        size = 4 + rng.random() * 4
        out.append(Particle(x, y, vx, vy, 0.3, SPLASH_COLOR, size))
    return out


def hop_dust(x: float, y: float, rng: CosmeticRng) -> list[Particle]:
    """跳んで着いた所の土ぼこり（原型の hop）。6 つ。見た目の乱数を 18 個引く。

    (x, y) は着いたプレイヤーの位置（マス）。粒は足元（0.3 マス下）から出る。
    """
    out = []
    for _ in range(6):
        vx = (rng.random() - 0.5) * 2
        vy = -rng.random() * 1.6
        size = 3 + rng.random() * 3
        out.append(Particle(x, y + 0.3, vx, vy, 0.35, DUST_COLOR, size))
    return out


def animal_emoji(animal: Animal) -> str:
    """動物の顔の絵文字（原型の ANIMALS の emoji）。倒れたときに浮かぶ。"""
    match animal:
        case Animal.RABBIT:
            return "\N{RABBIT FACE}"
        case Animal.ELEPHANT:
            return "\N{ELEPHANT}"
        case Animal.MOLE:
            # 原型はもぐらにビーバーの絵文字を当てている（もぐらの絵文字が無いため）。
            return "\N{BEAVER}"
        case Animal.FOX:
            return "\N{FOX FACE}"
        case Animal.FROG:
            return "\N{FROG FACE}"
        case _:
            assert_never(animal)
