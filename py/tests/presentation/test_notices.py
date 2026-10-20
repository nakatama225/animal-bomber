"""通知の文（原型の `toast` の 22 種）の検査。

文の写し違いは、欄に原型の `${…}` を入れた文が、原型（`legacy/animal-bomber.html`）の
ファイルの中にそのまま見つかるかで見る（絵文字の見え方を選ぶ印 U+FE0F まで比べる）。
原型の `toast(`・`flash(` の呼び出しの行が 22 あり、どの行もこの版の文のどれかに
当たることも見る（写し漏れを見つけるため）。
"""

import re
from functools import cache
from pathlib import Path

import pytest

from animal_bomber.domain.abilities.mole import HOLD_TIME
from animal_bomber.domain.events import SuddenDeathReason
from animal_bomber.presentation import notices

LEGACY = Path(__file__).resolve().parents[3] / "legacy" / "animal-bomber.html"

NAME = "${p.animal.name}"
"""原型の、動物の名前の差し込み。"""

FILLED: dict[str, str] = {
    "SLIPPED": notices.SLIPPED.format(name=NAME, doubled="${bonus}"),
    "CRIED": notices.CRIED.format(name=NAME, doubled="${bonus}"),
    "CHICKEN": notices.CHICKEN.format(
        name=NAME,
        special="${specialOf(p.animal.key).name}",
        times="${M>1?` ×${M}`:''}",
    ),
    "POOPED": notices.POOPED.format(
        name=NAME, label="${POOPS[k].label}", doubled="${bonus}"
    ),
    "TO_LANE": notices.TO_LANE.format(name=NAME),
    "REVIVED": notices.REVIVED.format(
        shooter="${shooter.label}", victim="${victim.label}"
    ),
    "LANES_CLOSED": f"'{notices.LANES_CLOSED}'",
    "TONGUE_BURNT": notices.TONGUE_BURNT.format(name=NAME, reach="${p.tongueLimit}"),
    "TONGUE_GONE": notices.TONGUE_GONE.format(
        name=NAME, seconds="${Math.ceil(p.tongueRegen)}"
    ),
    "PIT_DUG": notices.PIT_DUG.format(name=NAME),
    "PIT_FALLEN": notices.PIT_FALLEN.format(name=NAME, seconds="${PIT_HOLD}"),
    "SPECIAL_USED": notices.SPECIAL_USED.format(
        emoji="${SP.emoji}", name=NAME, special="${SP.name}"
    ),
    "SWEPT": notices.SWEPT.format(
        emoji="${def.emoji}", name=NAME, label="${def.label}"
    ),
    "PUSHED": notices.PUSHED.format(
        name=NAME, target="${q.animal.name}", count="${carry.length}"
    ),
    "SPRAYED": notices.SPRAYED.format(name=NAME, what="${msg.join('・')}"),
    "PAD_UNSUPPORTED": notices.PAD_UNSUPPORTED.format(pad="${gp.id}"),
    "PAD_FOUND": f"'{notices.PAD_FOUND}'",
    "SERVER_LOST": f"'{notices.SERVER_LOST}'",
    "HOST_LOST": f"'{notices.HOST_LOST}'",
    "CPU_TOOK_OVER": notices.CPU_TOOK_OVER.format(name=NAME),
    "TONGUE_REGROWN": notices.TONGUE_REGROWN.format(
        name=NAME, reach="${p.tongueLimit}"
    ),
    "SUDDEN_DEATH": notices.SUDDEN_DEATH.format(
        reason="${why}",
        hp="1",
        bombs="${BOMB_MAX}",
        power="${POWER_MAX}",
        shoes="${SHOE_MAX}",
        seconds="60",
    ),
}
"""原型の `toast` の 22 種の文に、原型の差し込みを入れたもの。"""

PARTS: dict[str, str] = {
    "DOUBLED": f"'{notices.DOUBLED}'",
    "CHICKEN_TIMES": f"`{notices.CHICKEN_TIMES.format(times='${M}')}`",
    "DOUSED": notices.DOUSED.format(count="${nb}"),
    "WASHED": notices.WASHED.format(count="${np}"),
    "ALL_DOWN": f"'{notices.ALL_DOWN}'",
    "TIME_UP": f"'{notices.TIME_UP}'",
}
"""通知の文の部品に、原型の差し込みを入れたもの。"""


@cache
def legacy_text() -> str:
    return LEGACY.read_text(encoding="utf-8")


def toast_lines() -> list[str]:
    """原型の `toast(`・`flash(` を呼ぶ行（関数を定義する行は外す）。"""
    calls = re.compile(r"\b(?:toast|flash)\(")
    return [
        line
        for line in legacy_text().splitlines()
        if calls.search(line) and not line.lstrip().startswith("function")
    ]


class Test原型の文:
    @pytest.mark.parametrize("key", sorted(FILLED))
    def test_通知の文は_原型の文と同じ(self, key: str) -> None:
        assert FILLED[key] in legacy_text()

    @pytest.mark.parametrize("key", sorted(PARTS))
    def test_通知の部品は_原型の文と同じ(self, key: str) -> None:
        assert PARTS[key] in legacy_text()

    def test_原型の通知は22種で_どれもこの版の文に当たる(self) -> None:
        lines = toast_lines()
        assert len(lines) == 22
        unmatched = [
            line.strip()
            for line in lines
            if not any(filled in line for filled in FILLED.values())
        ]
        assert unmatched == []
        assert len(FILLED) == 22


class Test差し込んだ文:
    def test_効果が2倍の動物にだけ_2倍と添える(self) -> None:
        assert notices.slipped("かえる", 2) == "🍌 かえる すべる！（2倍！）"
        assert notices.slipped("うさぎ", 1) == "🍌 うさぎ すべる！"
        assert notices.cried("かえる", 2) == "🧅 かえる 涙で動けない！（2倍！）"
        assert notices.pooped("ぞう", "超スロー", 1) == "💩 ぞう 超スロー！"
        assert notices.pooped("かえる", "超スロー", 2).endswith("（2倍！）")

    def test_チキンの回数は_2回ぶん溜まるときだけ_空白とかけるで添える(self) -> None:
        assert (
            notices.chicken_taken("かえる", "粘膜爆弾", 2)
            == "🍗 かえる とくぎ「粘膜爆弾」 ×2！"
        )
        assert (
            notices.chicken_taken("うさぎ", "うんこポロポロ", 1)
            == "🍗 うさぎ とくぎ「うんこポロポロ」！"
        )

    def test_鼻水は_消したものだけを並べ_何も消さなければ出さない(self) -> None:
        assert notices.sprayed("ぞう", 0, 0) is None
        assert notices.sprayed("ぞう", 2, 0) == "💧 ぞう 鼻水で 爆弾2個の火を消した！"
        assert notices.sprayed("ぞう", 0, 3) == "💧 ぞう 鼻水で うんこ3個を流した！"
        assert (
            notices.sprayed("ぞう", 1, 1)
            == "💧 ぞう 鼻水で 爆弾1個の火を消した・うんこ1個を流した！"
        )

    def test_秒は切り上げる(self) -> None:
        """原型の `Math.ceil(p.tongueRegen)`。600 tick（10 秒）で1マス戻る。"""
        assert notices.tongue_gone("かえる", 600) == (
            "👅🔥 かえる の舌は焼け落ちてる（10秒で1マス戻る）"
        )
        assert "（10秒で" in notices.tongue_gone("かえる", 541)
        assert "（9秒で" in notices.tongue_gone("かえる", 540)
        assert "（1秒で" in notices.tongue_gone("かえる", 1)

    def test_落とし穴は3秒うごけない(self) -> None:
        assert (
            notices.pit_fallen("うさぎ", HOLD_TIME)
            == "\N{HOLE}\N{VARIATION SELECTOR-16} うさぎ 落とし穴！ 3秒うごけない"
        )

    def test_延長戦の通知は_わけと_延長戦の決まりの値(self) -> None:
        assert notices.sudden_death(SuddenDeathReason.ALL_DOWN) == (
            "⚡ サドンデス！（同時にやられた） 全員HP1・💣13・🔥13・👟13・60秒"
        )
        assert notices.sudden_death(SuddenDeathReason.TIME_UP) == (
            "⚡ サドンデス！（時間切れ） 全員HP1・💣13・🔥13・👟13・60秒"
        )

    def test_試合の外の通知(self) -> None:
        assert (
            notices.cpu_took_over("うさぎ") == "うさぎ の回線が切れた → CPU が引き継ぐ"
        )
        assert (
            notices.pad_unsupported("Pad (Vendor: 1)")
            == "🎮 このコントローラーには対応していません（Pad (Vendor: 1)）"
        )
