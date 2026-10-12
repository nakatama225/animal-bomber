"""動物・振る舞い・盤面の物の種類を、共通の処理が知らないことの検査。

試合を進める処理（`domain/systems/`）・盤面への問い合わせ（`domain/query/`）・イベント
（`domain/events.py`）は、何の動物か・何の振る舞いか・何の盤面の物かを見ない。見るのは
性質（`state/actions.py` の `traits_of`、`rules/animals.py` の数値）だけで、種類で
分けるのは `domain/abilities/techniques.py`・`state/actions.py`・`state/actors.py`・
`rules/animals.py` の `match` だけにしてある。そこには `assert_never` があるので、種類を
足すと扱いの書き忘れを型検査が見つける。共通の処理に種類が漏れ出すと、その書き忘れは
型検査では見つからない。

突進は移動・破壊・取得・被弾の4つに同時に割り込むので、いちばん特別扱いを誘いやすい。
共通の処理に突進の名前が無いまま書けていることを、ここで見張る（TypeScript 版の
`guards.test.ts` の「動物の追加が閉じていること」と同じ見張り方）。

⚠️ ファイルの文字列をそのまま見ていて、コードとコメントを区別しない。コメントに動物の
名前を書くだけでも失敗する。原型の逸話を書くときも動物の名前は出さず、「ブロックを通り
抜ける動物」「効果が2倍になる動物」のように能力で書く。

名前を書かずに種類を見分ける書き方も禁じる。名前の文字列で比べる（`action_name`・
`actor_name`・`encode_action`・`encode_actor` の値）、型や属性の有無で見分ける
（`isinstance`・`hasattr`・`getattr`）の2つ。
"""

import re
from pathlib import Path
from typing import get_args

import pytest

from animal_bomber.domain.rules.animals import Animal
from animal_bomber.domain.state.actions import Action
from animal_bomber.domain.state.actors import Actor

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = ROOT / "src" / "animal_bomber" / "domain"

KIND_NAMES = (
    *(animal.value for animal in Animal),
    *(kind.__name__ for kind in (*get_args(Action), *get_args(Actor))),
)
"""動物の名前と、振る舞い・盤面の物のクラスの名前。

列挙と union から作るので、種類を足すと見張る名前も増える。
"""

KIND_WORDS = re.compile(
    r"Animal\."
    rf"|\b(?:{'|'.join(KIND_NAMES)})\b"
    r"|\b(?:action_name|actor_name|encode_action|encode_actor"
    r"|isinstance|hasattr|getattr)\b"
    r"|うさぎ|ぞう|もぐら|きつね|かえる|突進",
    # 大文字と小文字を区別しない（`Charge` も `charge` も拾う）。`\b` は英数字と `_`
    # だけを単語の文字として扱う。既定の `\b` はかなと漢字も単語の文字として扱うので、
    # 「`Charge`の」のように日本語に続けて書いた名前を見落とす。
    re.IGNORECASE | re.ASCII,
)
"""種類の名前と、名前を書かずに種類を見分ける書き方。"""


def watched() -> list[Path]:
    """種類を知ってはいけないファイル。"""
    return [
        *sorted((DOMAIN / "systems").glob("*.py")),
        *sorted((DOMAIN / "query").glob("*.py")),
        DOMAIN / "events.py",
    ]


class Test種類が閉じていること:
    def test_共通の処理に_動物と振る舞いと盤面の物の名前が現れない(self) -> None:
        offenders = [
            f"{path.relative_to(ROOT)}: {match.group(0)}"
            for path in watched()
            for match in KIND_WORDS.finditer(path.read_text(encoding="utf-8"))
        ]
        assert offenders == []

    def test_見張るファイルに_試合を進める処理と問い合わせとイベントが入っている(
        self,
    ) -> None:
        """見張るファイルの一覧が空だと、上の確かめは何も見ずに通る。"""
        names = {path.relative_to(DOMAIN).as_posix() for path in watched()}
        assert {
            "systems/actions.py",
            "systems/movement.py",
            "systems/items.py",
            "systems/damage.py",
            "systems/bomb.py",
            "query/board.py",
            "events.py",
        } <= names

    def test_見張る言葉が_種類を扱うファイルには現れる(self) -> None:
        """前の確かめが「その言葉がどこにも無いだけ」で通ってしまわないための対照。"""
        for name in ("abilities/elephant.py", "abilities/techniques.py"):
            text = (DOMAIN / name).read_text(encoding="utf-8")
            assert KIND_WORDS.search(text), name

    def test_見張る名前に_どの種類も入っている(self) -> None:
        """列挙や union から名前を取り出しそこねると、見張りが黙って狭くなる。"""
        assert len(KIND_NAMES) == len(Animal) + len(get_args(Action)) + len(
            get_args(Actor)
        )
        assert {"rabbit", "frog", "Charge", "Tongue", "Pit", "BurntTongue"} <= set(
            KIND_NAMES
        )

    @pytest.mark.parametrize(
        "line",
        [
            "# `Charge`の最中は止まる",
            "# moleの穴",
            'if action_name(player.action) == "charge":',
            'if actor_name(actor) == "slime":',
            "if isinstance(player.action, Moving):",
            'if hasattr(player.action, "carried"):',
            "case charge():",
        ],
    )
    def test_日本語に続けた名前と_名前を書かずに種類を見分ける書き方も拾う(
        self, line: str
    ) -> None:
        assert KIND_WORDS.search(line), line

    @pytest.mark.parametrize(
        "line",
        [
            "player.special_charges -= 1",
            "Moment.DIG_STARTED",
            "EffectKind.PITFALL",
            "# 火力を足す（spit ではない）",
        ],
    )
    def test_種類の名前を含むだけの別の言葉は拾わない(self, line: str) -> None:
        assert KIND_WORDS.search(line) is None, line
