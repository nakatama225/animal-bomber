"""入力の検査。"""

import pytest

from animal_bomber.domain.input.player_input import PlayerInput


class Test入力:
    def test_ビットの並びはTypeScript版と同じ(self) -> None:
        """記録の文字列と通信で送る値は、このビットの並びで決まる。"""
        assert [(i.name, int(i)) for i in PlayerInput] == [
            ("UP", 1),
            ("DOWN", 2),
            ("LEFT", 4),
            ("RIGHT", 8),
            ("BOMB", 16),
            ("ACTION", 32),
            ("SPECIAL", 64),
        ]

    def test_何も押していない入力は0で_偽として扱える(self) -> None:
        assert int(PlayerInput.IDLE) == 0
        assert not PlayerInput.IDLE

    def test_重ねた入力は整数にして戻しても同じ(self) -> None:
        held = PlayerInput.RIGHT | PlayerInput.BOMB
        assert PlayerInput(int(held)) == held
        assert PlayerInput.RIGHT in held
        assert PlayerInput.LEFT not in held

    @pytest.mark.parametrize("bits", [128, 129, 255, 256])
    def test_決めていないビットを含む整数からは作れない(self, bits: int) -> None:
        # 既定の IntFlag は黙って受け付ける。壊れた記録や通信の値を読んだ時点で止める。
        with pytest.raises(ValueError):
            PlayerInput(bits)

    @pytest.mark.parametrize(("bits", "expected"), [(-1, 127), (-128, 0)])
    def test_負の整数は_補数として受け付けてしまう(
        self, bits: int, expected: int
    ) -> None:
        """STRICT でも止まらない形を、振る舞いとして固定しておく。

        記録や通信の値を読む側で 0 未満を断る必要がある（`player_input.py` の冒頭）。
        Python の版でこの振る舞いが変わったら、ここが失敗して気づける。
        """
        assert int(PlayerInput(bits)) == expected

    def test_7つのボタンを全部押した値までは作れる(self) -> None:
        assert PlayerInput(127) == (
            PlayerInput.UP
            | PlayerInput.DOWN
            | PlayerInput.LEFT
            | PlayerInput.RIGHT
            | PlayerInput.BOMB
            | PlayerInput.ACTION
            | PlayerInput.SPECIAL
        )
