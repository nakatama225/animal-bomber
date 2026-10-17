"""描いた絵を取っておく仕組み（`render/sprites.py`）の検査。"""

import pygame
import pytest

from animal_bomber.presentation.render.canvas.protocol import Canvas
from animal_bomber.presentation.render.sprites import (
    SpriteCache,
    level_value,
    opacity,
    quantize,
)


def red_square(canvas: Canvas) -> None:
    canvas.fill_style = "#ff0000"
    canvas.fill_rect(10, 10, 8, 8)


class Test取っておく:
    def test_同じ鍵なら2回目は描き直さない(self) -> None:
        cache = SpriteCache()
        first = cache.get("a", (10, 10, 18, 18), red_square)
        second = cache.get("a", (10, 10, 18, 18), red_square)
        assert second is first
        assert cache.renders == 1

    def test_絵は盤面の座標で描いた位置を持つ(self) -> None:
        """描いた範囲の左上（整数。四方に 1px のゆとり）を持ち、貼るとそこに来る。"""
        cache = SpriteCache()
        sprite = cache.get("a", (9.5, 10.2, 18, 18), red_square)
        assert (sprite.left, sprite.top) == (8, 9)
        assert sprite.surface.get_size() == (11, 10)
        target = pygame.Surface((30, 30))
        sprite.blit(target)
        assert tuple(target.get_at((12, 12)))[:3] == (255, 0, 0)
        assert tuple(target.get_at((8, 8)))[:3] == (0, 0, 0)
        sprite.blit(target, 10, 0)  # ずらして貼る
        assert tuple(target.get_at((22, 12)))[:3] == (255, 0, 0)

    def test_上限を超えたら_長く使っていないものから捨てる(self) -> None:
        """入力の組み合わせが段の数より多く出ても、取っておく数が増え続けない。"""
        cache = SpriteCache(capacity=2)
        cache.get("a", (10, 10, 18, 18), red_square)
        cache.get("b", (10, 10, 18, 18), red_square)
        cache.get("a", (10, 10, 18, 18), red_square)  # a を使い直す
        cache.get("c", (10, 10, 18, 18), red_square)  # b が捨てられる
        assert len(cache) == 2
        cache.get("a", (10, 10, 18, 18), red_square)
        assert cache.renders == 3
        cache.get("b", (10, 10, 18, 18), red_square)
        assert cache.renders == 4


class Test薄めた写し:
    def test_不透明度ごとに写しを作り_同じ不透明度なら作り直さない(self) -> None:
        cache = SpriteCache()
        sprite = cache.get("a", (10, 10, 18, 18), red_square)
        half = cache.faded("a", sprite, 128)
        assert half.surface.get_at((4, 4)).a == pytest.approx(128, abs=1)
        assert sprite.surface.get_at((4, 4)).a == 255  # 元の絵は変えない
        assert cache.faded("a", sprite, 128) is half
        assert cache.faded("a", sprite, 64) is not half
        assert cache.faded_count == 2

    def test_不透明度_255_なら元の絵をそのまま使う(self) -> None:
        cache = SpriteCache()
        sprite = cache.get("a", (10, 10, 18, 18), red_square)
        assert cache.faded("a", sprite, 255) is sprite
        assert cache.faded_count == 0

    def test_255_のすぐ下でも薄める(self) -> None:
        """元の絵をそのまま使うのは 255 だけ。254 は写しを作って薄める。"""
        cache = SpriteCache()
        sprite = cache.get("a", (10, 10, 18, 18), red_square)
        almost = cache.faded("a", sprite, 254)
        assert almost is not sprite
        assert almost.surface.get_at((4, 4)).a == 254

    def test_薄めた写しの数にも上限がある(self) -> None:
        cache = SpriteCache(fade_capacity=3)
        sprite = cache.get("a", (10, 10, 18, 18), red_square)
        for alpha in range(10, 20):
            cache.faded("a", sprite, alpha)
        assert cache.faded_count == 3

    def test_薄めた写しは_貼るときに薄めるのと同じ見た目になる(self) -> None:
        """写しを作る計算と、set_alpha で貼るときの計算の差は丸めの 1〜2 段まで。"""
        cache = SpriteCache()
        sprite = cache.get("a", (10, 10, 18, 18), red_square)
        baked = pygame.Surface((30, 30))
        baked.fill((0, 0, 255))
        cache.faded("a", sprite, 100).blit(baked)
        by_alpha = pygame.Surface((30, 30))
        by_alpha.fill((0, 0, 255))
        copy = sprite.surface.copy()
        copy.set_alpha(100)
        by_alpha.blit(copy, (sprite.left, sprite.top))
        for x, y in ((12, 12), (5, 5)):
            a, b = baked.get_at((x, y)), by_alpha.get_at((x, y))
            assert all(abs(a[i] - b[i]) <= 2 for i in range(3))


class Test段に丸める:
    @pytest.mark.parametrize(
        ("value", "level"),
        [
            (0.0, 0),
            (0.024, 0),  # 段の幅 0.05 の半分より手前
            (0.026, 1),  # 半分を超えたら次の段
            (1.0, 20),
            (-0.3, 0),  # 範囲の外は端の段
            (1.7, 20),
        ],
    )
    def test_いちばん近い段に丸める(self, value: float, level: int) -> None:
        assert quantize(value, 0, 1, 21) == level

    def test_段の値は_範囲を等しく分けた値(self) -> None:
        assert level_value(0, -2, 2, 9) == -2
        assert level_value(4, -2, 2, 9) == 0
        assert level_value(8, -2, 2, 9) == 2

    def test_段の数が1以下は誤り(self) -> None:
        with pytest.raises(ValueError, match="段の数"):
            quantize(0.5, 0, 1, 1)

    def test_不透明度は_set_alpha_と同じく切り捨てて整数にする(self) -> None:
        """README の測定（薄めた絵を先に作る形）と同じ丸め。"""
        assert opacity(1.0) == 255
        assert opacity(0.5) == 127
        assert opacity(-0.1) == 0
        assert opacity(1.5) == 255
