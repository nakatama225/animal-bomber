"""描画の層を通した測定（`tools/bench_art.py`・`bench_art_scene.py`）の検査。

測った値は機械と負荷で変わるので見ない。見るのは、窓を開かずに走ること・決めた形で
結果を返すこと・場面が決めた描き方（薄れる絵を貼るたびに薄めない・測る間に絵を描かない）
で描くこと。どれも別のプロセスで走らせる（`runner.py`）。
"""

import json
import subprocess
import sys

from .runner import DUMMY_ENV, TOOLS, report_of

BENCH_ART = TOOLS / "bench_art.py"

COUNTING = f"""
import json, random, sys
sys.path.insert(0, {str(TOOLS)!r})
import pygame
from bench_art_scene import ArtScene, ArtSceneSpec
pygame.display.init()
assert pygame.display.get_driver() == "dummy"
spec = ArtSceneSpec(26, "glow", spinners=0)
pygame.display.set_mode(spec.size)
class Counting(pygame.Surface):
    def __init__(self, size):
        super().__init__(size)
        self.alpha_blits = self.faded_blits = 0
    def blit(self, source, dest, area=None, special_flags=0):
        if source.get_masks()[3]:
            self.alpha_blits += 1
            alpha = source.get_alpha()
            if alpha is not None and alpha < 255:
                self.faded_blits += 1
        return super().blit(source, dest, area, special_flags)
scene = ArtScene(spec, random.Random(1))
built = scene.renders
out = []
for frame in range(40):
    target = Counting(spec.size)
    scene.draw(target, frame)
    out.append([target.alpha_blits, target.faded_blits])
print(json.dumps({{"frames": out, "drawn": scene.renders - built,
                  "counts": scene.counts}}))
"""


def run_art(*args: str) -> subprocess.CompletedProcess[str]:
    """測定を、小さく（3 フレーム・前の 1 フレームを捨てる・JSON で）走らせる。"""
    return subprocess.run(
        [sys.executable, str(BENCH_ART), "--frames", "3", "--warmup", "1", "--json"]
        + list(args),
        env=DUMMY_ENV,
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_窓を開かずに描いて_結果をJSONで返す() -> None:
    """測定が、壊れたまま次に使うときまで放置されないためのもの。"""
    report = report_of(run_art("--tiles", "26", "--kinds", "glow"))
    assert report["driver"] == "dummy"
    assert report["measured_at"]
    [result] = report["results"]
    assert (result["tile"], result["width"], result["height"]) == (26, 630, 474)
    counts = [result[key] for key in ("blasts", "particles", "spinners")]
    assert counts + [result["players"], result["bombs"]] == [297, 105, 4, 4, 8]
    # フレームが 100 より少ないうえ、判定に使う行も測っていないので、合否は出さない。
    assert report["gate_passed"] is None


def test_場面は_取っておいた絵を薄めずに貼り_測る間に絵を描かない() -> None:
    """場面が黙って軽く（または重く）なる誤りを、貼った数で見つける。

    - 画素ごとの透明を持つ絵を、貼るたびに薄めない（描画の層の絵は、薄めた写しを貼る）。
      例外は回りながら浮かぶ顔（`bench_particles.py`）なので、ここでは顔を出さない
    - 先に描いておいた絵で足りること（測る間に描くと、そのフレームが遅れる）
    - 貼った数が、場面が持つ数より少なくない（爆風 297 件は2枚ずつ・アイテム 20 個は
      2枚か7枚ずつ・爆弾 8 個は4〜6枚ずつ・プレイヤー 4 体・粘膜爆弾・炎・光の玉 105）。
      プレイヤーは、接地影と輪・体・印の3枚に、かえるは舌の根元と吸盤の2枚以上、もぐらは
      掘る身ぶりの穴・土の山2つ・つるはし・ゲージ2枚の6枚以上、きつねはゲージ2枚を足す
      （合わせて 22 枚以上）。粘膜爆弾は影と体の1枚以上、炎は跡3マスと火の玉と芯の5枚
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
    assert seen["drawn"] == 0
    assert seen["counts"]["items"] == 20
    assert (seen["counts"]["slimes"], seen["counts"]["foxfires"]) == (1, 1)
    players = 4 * 3 + 2 + 6 + 2
    for alpha_blits, faded_blits in seen["frames"]:
        assert faded_blits == 0
        assert alpha_blits >= 297 * 2 + 20 * 2 + 8 * 4 + players + 1 + 5 + 105
