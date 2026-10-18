"""描画の重さの測定で描く場面（`tools/bench_match_scene.py`）が、決めた描き方で描くことの検査。

描く先を、貼った数を数える面に差し替えて、場面を描く。描き方の誤りの多くは、壊れても
場面は最後まで描け、時間だけが黙って軽く（または重く）出る。別のプロセスで走らせる
（`runner.py`）。
"""

import json
import subprocess
import sys

from .runner import DUMMY_ENV, TOOLS

COUNTING = f"""
import json, random, sys
sys.path.insert(0, {str(TOOLS)!r})
import pygame
from bench_match_scene import MatchScene, MatchSceneSpec
pygame.display.init()
assert pygame.display.get_driver() == "dummy"
out = {{}}
for kind in ("square", "glow"):
    spec = MatchSceneSpec(26, kind)
    pygame.display.set_mode(spec.size)
    class Counting(pygame.Surface):
        def __init__(self, size):
            super().__init__(size)
            self.alpha_blits = self.faded_blits = self.shaken_boards = 0
        def blit(self, source, dest, area=None, special_flags=0):
            if source.get_masks()[3]:
                self.alpha_blits += 1
                alpha = source.get_alpha()
                if alpha is not None and alpha < 255:
                    self.faded_blits += 1
            board = source.get_width() > self.get_width() // 2
            if board and special_flags == pygame.BLEND_PREMULTIPLIED:
                self.shaken_boards += 1
            return super().blit(source, dest, area, special_flags)
    scene = MatchScene(spec, random.Random(1))
    built = scene.renders
    frames = []
    shaken = []
    for frame in range(40):
        target = Counting(spec.size)
        scene.draw(target, frame)
        frames.append([target.alpha_blits, target.faded_blits])
        shaken.append(target.shaken_boards)
    out[kind] = {{"frames": frames, "drawn": scene.renders - built,
                  "counts": scene.counts, "phases": scene.blast_phases,
                  "shaken": shaken}}
print(json.dumps(out))
"""


def test_場面は_取っておいた絵を薄めずに貼り_測る間に絵を描かない() -> None:
    """場面が黙って軽く（または重く）なる誤りを、貼った数で見つける。

    - 画素ごとの透明を持つ絵を、貼るたびに薄めない（描画の層は、薄めた写しを貼る。
      回りながら浮かぶ顔も、薄めた形の絵を作って重ねる）
    - 先に描いておいた絵で足りること（測る間に描くと、そのフレームが遅れる）
    - 爆風の位相をそろえていること（そろえ損ねると軽く測れる）
    - 画面がいつも揺れていること（揺れが止まると、背景と盤面を合わせた1枚を貼る軽い
      ほうの道を通る）。揺れているフレームは、盤面の大きさの絵を、色に不透明度を掛けた
      形で1回貼る。ずれが縦横とも 0px に丸まるフレーム（100 回に 1 回ほど）だけは
      1枚で貼る
    - 貼った数が、場面が持つ数より少なくない：爆風 297 件は2枚ずつ・アイテム
      20 個は2枚か7枚ずつ・爆弾 8 個は4〜6枚ずつ・プレイヤー 4 体（接地影と輪・体・印の
      3枚に、かえるは舌の根元と吸盤の2枚以上、もぐらは掘る身ぶりの穴・土の山2つ・
      つるはし・ゲージ2枚の6枚以上、きつねはゲージ2枚）・粘膜爆弾1枚以上・炎（火の玉と
      芯と跡）・粒子 105 個と顔 4 個
    """
    completed = subprocess.run(
        [sys.executable, "-c", COUNTING],
        env=DUMMY_ENV,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 0, completed.stderr
    # pygame は読み込んだときに挨拶の行を出すので、最後の行を読む。
    seen = json.loads(completed.stdout.strip().splitlines()[-1])
    players = 4 * 3 + 2 + 6 + 2
    for kind in ("square", "glow"):
        result = seen[kind]
        assert result["drawn"] == 0
        assert result["phases"] == 1
        shaken = result["shaken"]
        assert set(shaken) <= {0, 1}
        assert sum(shaken) >= len(shaken) - 2
        counts = result["counts"]
        assert [counts[key] for key in ("blasts", "particles", "spinners")] == [
            297,
            105,
            4,
        ]
        assert (counts["players"], counts["bombs"], counts["items"]) == (4, 8, 20)
        fire = 2 + counts["trail"]
        least = 297 * 2 + 20 * 2 + 8 * 4 + players + 1 + fire
        least += 105 if kind == "square" else 0
        for alpha_blits, faded_blits in result["frames"]:
            assert faded_blits == 0
            assert alpha_blits >= least
