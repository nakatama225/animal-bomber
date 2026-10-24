"""画面の色と寸法（原型の CSS の値。`legacy/animal-bomber.html` の L8-238）。

色の名前は原型の `:root` の変数（L8-12）と同じにした。字の大きさだけ `css_px` で整数に
丸める（端数 0.5 は大きいほうへ。11.5px は 12px、10.5px は 11px）。文を描く所
（`render/ui/typeset.py`）は `pygame.font` で書いてあり、`pygame.font` は整数の
大きさしか受け取らない。`pygame.freetype` は端数を受け取るが、字の送りが整数の画素に
そろい、11.5px は 12px とほぼ同じ幅になる。色の絵文字も1色になる。
"""

import math
from typing import Final, TypeAlias

Color: TypeAlias = tuple[int, int, int]
"""色（赤・緑・青。0〜255）。"""


def hex_color(text: str) -> Color:
    """`#rrggbb` の色。

    Raises:
        ValueError: `#` と16進の6桁でないとき。
    """
    if len(text) != 7 or not text.startswith("#"):
        raise ValueError(f"#rrggbb の形でない色: {text!r}")
    value = int(text[1:], 16)
    return (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF


def css_px(size: float) -> int:
    """CSS の字の大きさ（px）を、`pygame.font` の書体に渡せる整数にする。

    端数 0.5 は大きいほうへ丸める（11.5px は 12px）。`pygame.font` は整数の大きさしか
    受け取らない（`pygame.freetype` を使わない理由はモジュールの説明）。
    """
    return max(1, math.floor(size + 0.5))


def mix(color: Color, under: Color, opacity: float) -> Color:
    """`color` を不透明度 `opacity` で `under` に重ねた色（CSS の opacity の結果）。"""
    return (
        round(color[0] * opacity + under[0] * (1 - opacity)),
        round(color[1] * opacity + under[1] * (1 - opacity)),
        round(color[2] * opacity + under[2] * (1 - opacity)),
    )


BG: Final = hex_color("#2a1d16")
"""原型の `--bg`。"""
INK: Final = hex_color("#fff6ec")
"""文字の色（原型の `--ink`）。"""
DIM: Final = hex_color("#c9ab97")
"""淡い文字・注記（原型の `--dim`）。"""
ACCENT: Final = hex_color("#ff8a3d")
"""押せる物の縁・選ばれたチップ（原型の `--accent`）。"""
ACCENT2: Final = hex_color("#ffd23f")
"""見出しのラベル・★・強調（原型の `--accent2`）。"""
NG: Final = hex_color("#ff5f5f")
"""残り 30 秒の時計・MAJOR（原型の `--ng`）。"""
PANEL: Final = hex_color("#402e23")
"""横の板の箱（原型の `--panel`）。"""
LINE: Final = hex_color("#5c4433")
"""枠線（原型の `--line`）。"""
BOARD_FILL: Final = hex_color("#1b120d")
"""盤面の枠の内側の地（原型の canvas の `background:#1b120d`。L73）。"""

FIELD: Final = hex_color("#2d2019")
"""チップ・動物のカード・小さいボタン・更新履歴の箱・確認の画面の地（原型 L35）。"""
CARD_TOP: Final = hex_color("#4a3527")
"""カードと大きいメニューのボタンのグラデーションの上（原型の `.card`・`.mbtn`）。"""
CARD_BOTTOM: Final = hex_color("#33241b")
"""カードと大きいメニューのボタンのグラデーションの下。"""
SELECTED_SHADOW: Final = hex_color("#8a3d12")
"""選ばれたチップとカードの下の影（原型の `box-shadow:0 4px 0 #8a3d12`）。"""
CHIP_ON_BOTTOM: Final = hex_color("#e0651f")
"""選ばれたチップのグラデーションの下（上は `ACCENT`。原型 L39）。"""
CHIP_ON_INK: Final = hex_color("#2a1206")
"""選ばれたチップの字（原型 L40）。"""
CARD_ON: Final = hex_color("#4a3120")
"""選ばれた動物のカードの地（原型 L46）。"""
GO_TOP: Final = hex_color("#ffd23f")
"""大きいボタンのグラデーションの上（原型の `.go`。L56）。"""
GO_BOTTOM: Final = hex_color("#ff9b1e")
"""大きいボタンのグラデーションの下。"""
GO_INK: Final = hex_color("#3a1a02")
"""大きいボタンの字。"""
GO_SHADOW: Final = hex_color("#b56411")
"""大きいボタンの下の影（原型の `0 6px 0 #b56411`）。"""
KEY_FILL: Final = hex_color("#241a14")
"""キーの形の地（原型の `.keyhelp .k`）。"""
TAG_HUMAN: Final = hex_color("#5c4433")
"""名札の人間の札（原型の `.tag`）。"""
TAG_CPU: Final = hex_color("#3d5c6b")
"""名札の CPU の札（原型の `.tag.cpu`）。"""
TAG_NEGIBON: Final = hex_color("#4d7a1f")
"""名札の葱ボンの札（原型の `.tag.negi`）。"""
NEGIBON_RIM: Final = hex_color("#9bd85c")
"""外周にいるプレイヤーの名札の枠（原型の `.pcard.negi`）。"""
PLATE_TOP: Final = hex_color("#e0452c")
"""ロゴの銘板のグラデーションの上（原型の `.logoPlate`）。"""
PLATE_BOTTOM: Final = hex_color("#b8301c")
"""ロゴの銘板のグラデーションの下。"""
PLATE_RIM: Final = hex_color("#ffd9c9")
"""ロゴの銘板の縁。"""
LOGO_SHADOW_NEAR: Final = hex_color("#8f2b1c")
"""ロゴの字の影の近いほう（原型の `0 4px 0 #8f2b1c`）。"""
LOGO_SHADOW_FAR: Final = hex_color("#5d1a10")
"""ロゴの字の影の遠いほう（原型の `0 9px 0 #5d1a10`）。"""
WHITE: Final = (255, 255, 255)
"""カーソルの枠の色（原型の `.navcur{outline:3px solid #fff}`）。"""

PAGE_STOPS: Final = (
    (0.0, hex_color("#4a3527")),
    (0.6, hex_color("#241812")),
    (1.0, hex_color("#1a110d")),
)
"""画面の背景の円形のグラデーション（原型の `body` の `radial-gradient`。L14-15）。"""
PAGE_RADII: Final = (1200, 700)
"""画面の背景のグラデーションの楕円の半径（px）。"""
PAGE_CENTER: Final = (0.5, -0.1)
"""画面の背景のグラデーションの中心（窓の幅と高さに対する割合）。"""

SPLASH_STOPS: Final = (
    (0.0, hex_color("#4a3527")),
    (0.75, hex_color("#1a110d")),
)
"""起動の幕の背景（原型の `#splash` の `radial-gradient`。L178）。"""
SPLASH_RADII: Final = (700, 500)
"""起動の幕の背景の楕円の半径（px）。"""
SPLASH_CENTER: Final = (0.5, 0.4)
"""起動の幕の背景の中心（窓の幅と高さに対する割合）。"""

PAGE_PADDING: Final = 16
"""画面のまわりの余白（原型の `body{padding:16px}`）。"""
APP_MAX_WIDTH: Final = 1140
"""画面の中身の幅の上限（原型の `#app{max-width:1140px}`）。"""
MENU_MAX_WIDTH: Final = 520
"""縦に並ぶメニューの幅の上限（原型の `.menu{max-width:520px}`）。"""
BORDER: Final = 2
"""箱の枠の太さ（原型の `border:2px solid`）。"""

FOCUS_WIDTH: Final = 3
"""カーソルの白い枠の太さ（原型の `outline:3px`）。"""
FOCUS_OFFSET: Final = 2
"""カーソルの白い枠と項目の間（原型の `outline-offset:2px`）。

原型の注記：チップの間は 8px なので、5px 以上にすると枠が隣のチップに触る。
"""
