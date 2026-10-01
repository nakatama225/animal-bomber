"""描画の重さを測る場面（`tools/bench_scene.py` ほか）が、決めた描き方で描くことの検査。

描く先を、塗りと貼りを数える面に差し替えて、場面を描く。描き方の誤りの多くは、
壊れても場面は最後まで描け、時間だけが黙って軽く（または重く）出る。見た目が
変わらないことは `test_bench_render.py` が画素で確かめる。

描き方を変えたら（AGENTS.md の「描画の重さ」）、ここの数も直す。
"""

import json

from .runner import report_of, run_bench, run_patched

# 描く先を、塗りと貼りを数える面にして、場面を 1 周（BLAST_TICKS フレーム）描く。
# 画素ごとの透明を持つ絵かどうかは get_masks()[3] で見分ける（get_flags() の
# SRCALPHA は、不透明な絵でも set_alpha したあとに立つので使えない）。
COUNTING = """
import json
import random
import pygame
from bench_scene import BLAST_TICKS, Scene, SceneSpec
pygame.display.init()
assert pygame.display.get_driver() == "dummy"
pygame.display.set_mode((630, 474))
class Counting(pygame.Surface):
    def __init__(self, size):
        super().__init__(size)
        self.fills = self.alpha_blits = self.faded_blits = 0
    def fill(self, color, rect=None, special_flags=0):
        self.fills += 1
        return super().fill(color, rect, special_flags)
    def blit(self, source, dest, area=None, special_flags=0):
        if source.get_masks()[3]:
            self.alpha_blits += 1
            alpha = source.get_alpha()
            if alpha is not None and alpha < 255:
                self.faded_blits += 1
        return super().blit(source, dest, area, special_flags)
def counts(fade, spinners):
    scene = Scene(SceneSpec(26, "glow", fade=fade, spinners=spinners), random.Random(1))
    out = []
    for frame in range(BLAST_TICKS):
        target = Counting((630, 474))
        scene.draw(target, frame)
        out.append([target.fills, target.alpha_blits, target.faded_blits])
    return out
print(json.dumps({
    "baked": counts("baked", 0),
    "alpha": counts("alpha", 0),
    "spinners": counts("baked", 4),
}))
"""


class TestScene:
    def test_1周描くと_位相が進み_持っている数だけ貼り_先に作った絵は薄めずに貼る(
        self,
    ) -> None:
        """描き方が黙って軽く（または重く）なる誤りを、塗りと貼りの数で見つける。

        - 位相が進まないと、毎フレーム出たての爆風になり、薄れた絵を貼るフレームが
          無くなって軽く測れる
        - 描くループを削ったり、描く数を減らしたりしても、場面が持っている数
          （JSON の数）は変わらない
        - 先に作っておく形（baked）のはずが、貼るたびに薄める重い経路を通っていると、
          README の2つの形の比べが黙って入れ替わる

        blit を 1 回ずつ数えるので、正しい変更（blits にまとめる・描く順を変える）でも
        失敗する。そのときは数を直す。
        """
        completed = run_patched(COUNTING)
        assert completed.returncode == 0, completed.stderr
        seen = json.loads(completed.stdout)
        baked, alpha, spinners = seen["baked"], seen["alpha"], seen["spinners"]
        # 赤い下地は、残り 12〜28 刻み（k × 2.4 が 1 以上）ではマスを塗り、残り
        # 1〜11 刻みでは薄めて貼る。位相が進まないと、塗るフレームだけになる。
        assert [fills for fills, _, _ in baked] == [297] * 17 + [0] * 11
        # 画素ごとの透明を持つ絵は、爆弾 8・芯 297・プレイヤー 4・光の玉 105。
        # 回りながら浮かぶ顔 4 を足すと 418。
        assert {blits for _, blits, _ in baked} == {414}
        assert {blits for _, blits, _ in spinners} == {418}
        # 先に作っておく形では、画素ごとの透明を持つ絵を薄めて貼らない。貼るたびに
        # 薄める形では、光の玉 105 を毎フレーム、芯 297 を消え際の 9 フレームで薄める。
        assert [faded for _, _, faded in baked] == [0] * 28
        assert [faded for _, _, faded in alpha] == [105] * 19 + [402] * 9

    def test_位相を散らすと_位相の種類が1より多い(self) -> None:
        """位相の種類の数（blast_phases）を数える側が壊れていないこと。

        いつも 1 を返すように壊れると、位相をそろえ損ねても気づけない。
        """
        report = report_of(
            run_bench("--tiles", "26", "--kinds", "square", "--phases", "spread")
        )
        [result] = report["results"]
        assert result["phases"] == "spread"
        assert result["blast_phases"] > 1

    def test_faded_は写しを返し_元の絵を変えない(self) -> None:
        """元の絵を薄めると、同じ絵から作るほかの不透明度の写しまで薄くなる。"""
        completed = run_patched(
            "import pygame\n"
            "from bench_scene import CORE_STOPS\n"
            "from bench_sprites import faded, radial\n"
            "pygame.display.init()\n"
            "pygame.display.set_mode((64, 64))\n"
            "sprite = radial(20, CORE_STOPS)\n"
            "before = pygame.image.tobytes(sprite, 'RGBA')\n"
            "copy = faded(sprite, 128)\n"
            "after = pygame.image.tobytes(sprite, 'RGBA')\n"
            "print(copy is not sprite, after == before)\n"
        )
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.split() == ["True", "True"]

    def test_光の玉の薄れ方が1を超えたら_例外にする(self) -> None:
        """出たときより明るい値を、黙って端の値に寄せないこと（寿命の数え方の誤り）。

        0 より下は 0 にそろえる（TypeScript 版と同じ）。
        """
        completed = run_patched(
            "from bench_particles import _glow_alpha\n"
            "print(_glow_alpha(1.0), _glow_alpha(0.0), _glow_alpha(-0.5))\n"
            "_glow_alpha(1.01)\n"
        )
        assert completed.stdout.split() == ["204", "0", "0"]
        assert "光の玉の薄れ方は 1 以下になるはず: 1.01" in completed.stderr
