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
from animal_bomber.presentation.render.layout import PANEL_GAP, PANEL_WIDTH
pygame.display.init()
assert pygame.display.get_driver() == "dummy"
out = {{}}
for kind in ("square", "glow"):
    spec = MatchSceneSpec(26, kind)
    pygame.display.set_mode(spec.size)
    panel_left = spec.board_size[0] + PANEL_GAP
    class Counting(pygame.Surface):
        def __init__(self, size):
            super().__init__(size)
            self.alpha_blits = self.faded_blits = self.shaken_boards = 0
            self.spinner_blits = 0
            self.panels = []
            self.on_panel = 0
        def blit(self, source, dest, area=None, special_flags=0):
            if source.get_masks()[3]:
                self.alpha_blits += 1
                alpha = source.get_alpha()
                if alpha is not None and alpha < 255:
                    self.faded_blits += 1
            board = source.get_width() > self.get_width() // 2
            if special_flags == pygame.BLEND_PREMULTIPLIED:
                if board:
                    self.shaken_boards += 1
                else:
                    self.spinner_blits += 1
            x = dest[0] if isinstance(dest, tuple) else dest.x
            if x >= panel_left:
                self.on_panel += 1
                if source.get_width() == PANEL_WIDTH:
                    self.panels.append([bool(source.get_masks()[3]),
                                        source.get_alpha(), special_flags])
            return super().blit(source, dest, area, special_flags)
    scene = MatchScene(spec, random.Random(1))
    built = scene.renders
    frames = []
    shaken = []
    spinners = []
    panels = []
    for frame in range(40):
        target = Counting(spec.size)
        scene.draw(target, frame)
        frames.append([target.alpha_blits, target.faded_blits])
        shaken.append(target.shaken_boards)
        spinners.append(target.spinner_blits)
        panels.append([target.panels, target.on_panel])
    out[kind] = {{"frames": frames, "drawn": scene.renders - built,
                  "counts": scene.counts, "phases": scene.blast_phases,
                  "shaken": shaken, "spinners": spinners, "panels": panels,
                  "panel_builds": scene.panel_builds}}
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
      芯と跡）・粒子 105 個（四角い粒の行）
    - 回りながら浮かぶ顔 4 個を、どのフレームにも貼っている。顔は、色に不透明度を掛けた
      形で貼った小さい絵（幅が描く先の半分以下）の数で数える（ほかに同じ形で貼るのは、
      揺れている間の盤面の1枚だけ）。上の下限は余りが大きく、顔が消えても下回らない
    - 横の板を、どのフレームにも貼っている。板の位置に貼るのは、板の幅のアルファの桁の
      無い1枚（薄めず、色に不透明度を掛けた形でもない）と、時計の数字の小さい1枚の
      2枚だけ（板の中の箱や文を、毎フレーム1つずつ貼らない）
    - 板の絵は、名札の中身が変わるたびに作り直す（場面はきつねのとくぎの回数を
      15 フレームごとに変えるので、40 フレームで 0・15・30 フレーム目の3回）
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
        assert result["spinners"] == [counts["spinners"]] * len(result["spinners"])
        fire = 2 + counts["trail"]
        least = 297 * 2 + 20 * 2 + 8 * 4 + players + 1 + fire
        least += 105 if kind == "square" else 0
        for alpha_blits, faded_blits in result["frames"]:
            assert faded_blits == 0
            assert alpha_blits >= least
        for panel_blits, on_panel in result["panels"]:
            assert panel_blits == [[False, None, 0]]
            assert on_panel == 2
        assert result["panel_builds"] == 3
