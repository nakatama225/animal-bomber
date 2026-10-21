"""画面の文と盤面の絵の両方に出す絵文字の表（落とし穴・つるはし・うんこでかかる状態・アイテム）。

文と値を作る側（`hud/`・`notices.py`・`presenter.py`）と、描く側（`render/art/`）が同じ
字を使うので、ここに1か所だけ書く。描く側がここを読み、文の側は描く側を読まない
（`pyproject.toml` の import-linter の「文と値を作る側は描く側を import しない」）。
動物の絵文字ととくぎの絵文字は、動物の文と一緒に `animal_text.py` に置いてある。

値は原型（`legacy/animal-bomber.html`）の絵文字と、見え方を選ぶ印 U+FE0F まで同じ
文字列にする。
"""

from typing import Final, assert_never

from animal_bomber.domain.rules.items import ItemKind
from animal_bomber.domain.state.effects import EffectKind

HOLE: Final = "\N{HOLE}\N{VARIATION SELECTOR-16}"
"""落とし穴の絵文字（原型の 🕳️。見え方を選ぶ印 U+FE0F まで同じ文字列にする）。"""

PICK: Final = "\N{PICK}\N{VARIATION SELECTOR-16}"
"""つるはしの絵文字（原型の ⛏️）。"""

POOP_MARKS: Final = (
    (EffectKind.REVERSE, "\N{ANTICLOCKWISE DOWNWARDS AND UPWARDS OPEN CIRCLE ARROWS}"),
    (EffectKind.NOBOMB, "\N{NO ENTRY SIGN}"),
    (EffectKind.RUNAWAY, "\N{DASH SYMBOL}"),
    (EffectKind.WEAK, "\N{CANDLE}\N{VARIATION SELECTOR-16}"),
    (EffectKind.AUTOBOMB, "\N{SLOT MACHINE}"),
    (EffectKind.SLOW, "\N{SNAIL}"),
)
"""うんこでかかる状態と、その印（原型の POOP_KEYS の並びと POOPS の emoji）。

並びは原型の POOPS に書いた順（そうさ反転・爆弾おけない・とまれない・爆風1マス・勝手に
設置・超スロー）。`EffectKind` の定義の順とは違うので、ここに並べ直してある。
"""


def item_emoji(kind: ItemKind) -> str:
    """アイテムの絵文字（原型の ITEM_DEF の emoji）。"""
    match kind:
        case ItemKind.BOMB:
            return "💣"
        case ItemKind.FIRE:
            return "🔥"
        case ItemKind.SHOE:
            return "👟"
        case ItemKind.BANANA:
            return "🍌"
        case ItemKind.ONION:
            return "🧅"
        case ItemKind.CHICKEN:
            return "🍗"
        case ItemKind.POOP:
            return "💩"
        case _:
            assert_never(kind)
