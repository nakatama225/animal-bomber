"""動物の、画面に出す文（名前・絵文字・説明・とくぎの名前と絵文字・技の見出し）。

値は原型（`legacy/animal-bomber.html`）の `ANIMALS`（L679-707）・`SPECIALS`
（L751-760）・`skillLabelOf`（L5551-5558）から逐語で写した。ルールの層
（`domain/rules/animals.py`）には置かない。文を変えても試合は変わらず、能力を変えても文は
変わらない（変わる理由が違う）。

動物の顔の絵文字（`animal_emoji`）ととくぎの絵文字（`special_emoji`）は、盤面の絵
（倒れたときに浮かぶ顔・外周の鍋に乗る顔・足元の印）にも出す。描く側
（`render/art/`）がここを読み、ここは描く側を読まない（同じ字を2か所に書かない。
`presentation/emoji.py` の説明）。

## 原型の文から言い換えた所

リポジトリの文の決まり（書かない語）に当たる所だけ、熟語に言い換えてある。原型の語は
その書かない語なので、ここには書かない（言い換える前と後の組は
`tests/presentation/test_animal_text.py` の `REWORDED` に、字の番号で書いてある）。

- もぐらの説明（L694）の「👟の」に続く2字を「効果」にした（「👟の効果は通常と同じ倍率で
  伸びる」）
"""

from typing import Final, assert_never

from animal_bomber.domain.rules.animals import Animal
from animal_bomber.presentation.emoji import HOLE

ANIMAL_ORDER: Final = tuple(Animal)
"""動物を画面に並べる順（うさぎ・ぞう・もぐら・きつね・かえる）。

原型の `ANIMAL_LIST`（`ANIMALS` に書いた順）と同じ。CPU の動物は、この順の一覧から
人間が選ばなかったものを抜き出して混ぜる（`menu/local_setup.py`）。混ぜる前の並びが
違うと、同じ種でも TypeScript 版と別の顔ぶれになる。
"""

NO_PLAYER_SKILL_LABEL: Final = "技"
"""技のボタンの見出しで、プレイヤーが分からないとき（原型 `skillLabelOf` の1行目）。"""


def animal_name(animal: Animal) -> str:
    """動物の名前（原型の `ANIMALS` の `name`）。"""
    match animal:
        case Animal.RABBIT:
            return "うさぎ"
        case Animal.ELEPHANT:
            return "ぞう"
        case Animal.MOLE:
            return "もぐら"
        case Animal.FOX:
            return "きつね"
        case Animal.FROG:
            return "かえる"
        case _:
            assert_never(animal)


def animal_emoji(animal: Animal) -> str:
    """動物の顔の絵文字（原型の ANIMALS の emoji）。

    名札・幕・キャラ選びのほか、倒れたときに浮かぶ顔（`render/scene/particles.py`）と、
    外周の鍋に乗る顔（`render/art/negibons.py`）にも出す。
    """
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


def animal_description(animal: Animal) -> str:
    """キャラ選びのカードに出す説明（原型の `ANIMALS` の `desc`）。"""
    match animal:
        case Animal.RABBIT:
            return (
                "移動が速い。1マス跳んでブロックを越える（2秒に1回）。"
                "とくぎ「うんこポロポロ」＝周囲5×5の25マスを埋め尽くす"
                "（爆風でも消えず1分残る・自分は平気）"
            )
        case Animal.ELEPHANT:
            return (
                "爆風+2、HP+1。鼻水噴射は正面2マスの爆弾とうんこを消す（5秒に1回）。"
                "とくぎ「突進」＝1.5秒長押して柱までブロックを壊しながら直進する"
                "（爆風を受けると0.5ダメージ）"
            )
        case Animal.MOLE:
            return (
                "ソフトブロックのみ通り抜け可能"
                "（通り抜け中はとても遅いが、👟の効果は通常と同じ倍率で伸びる）。"
                "とくぎ「落とし穴」穴に落ちると3秒動けない（自分には発動しない）"
            )
        case Animal.FOX:
            return (
                "爆弾を最初から1個多く持つ。"
                "技ボタンで「1マス前」から手持ちぶん一列ドン設置。"
                "とくぎ「狐火」＝青い炎が1.5秒 敵を追いかける。"
                "放つ時にキツネ跳びで1秒 無敵"
            )
        case Animal.FROG:
            return (
                "舌で遠くのアイテムを引き寄せる（良いも悪いも全部食う）。"
                "アイテムの効果が2倍。"
                "とくぎ「粘膜爆弾」＝3マス先へ飛ばして跳ね回ってから爆発"
                "（アイテム2倍なので2回ぶん持てる）"
            )
        case _:
            assert_never(animal)


def special_name(animal: Animal) -> str:
    """その動物のとくぎの名前（原型の `SPECIALS` の `name`）。

    とくぎは🍗（チキン）を拾うと1回使える。名前は通知・名札・キーの案内に出す。
    """
    match animal:
        case Animal.RABBIT:
            return "うんこポロポロ"
        case Animal.ELEPHANT:
            return "突進"
        case Animal.MOLE:
            return "落とし穴"
        case Animal.FOX:
            return "狐火"
        case Animal.FROG:
            return "粘膜爆弾"
        case _:
            assert_never(animal)


def special_emoji(animal: Animal) -> str:
    """その動物のとくぎの絵文字（原型の SPECIALS の emoji）。

    名札・通知のほか、盤面の足元の印（`render/art/player_marks.py`）にも出す。
    """
    match animal:
        case Animal.RABBIT:
            return "\N{PILE OF POO}"
        case Animal.ELEPHANT:
            return "\N{BOAR}"
        case Animal.MOLE:
            return HOLE
        case Animal.FOX:
            return "\N{LARGE BLUE CIRCLE}"
        case Animal.FROG:
            return "\N{LARGE GREEN CIRCLE}"
        case _:
            assert_never(animal)


def skill_label(animal: Animal | None) -> str:
    """技のボタンの見出し（原型の `skillLabelOf`）。キーの案内の行の頭に出す。

    通常技を持たない動物（もぐら）は、技のボタンでもとくぎが出るので「とくぎ🍗」と
    書く（原型の注記 L5550）。

    Args:
        animal: そのボタンを使うプレイヤーの動物。分からなければ None（「技」）。
    """
    if animal is None:
        return NO_PLAYER_SKILL_LABEL
    match animal:
        case Animal.RABBIT:
            return "とぶ"
        case Animal.FROG:
            return "した"
        case Animal.FOX:
            return "ドン置き"
        case Animal.ELEPHANT:
            return "はなみず"
        case Animal.MOLE:
            return "とくぎ🍗"
        case _:
            assert_never(animal)
