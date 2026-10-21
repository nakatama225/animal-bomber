"""描画の重さの測定が、決めたとおりに測って出すことの検査（測った値によらない形で）。

`test_bench_render.py` は、窓を開かないことと結果の形を見る。ここでは、測る範囲・
列の値・眠り方・負荷を、時計を差し替えて確かめる。どれも、壊れても測定は最後まで
走り、それらしい数字を出す種類の誤りで（判定が黙って甘くなるものもある）、読み直しで
見つかった。描き方の数は `test_bench_match_scene.py` が確かめる。

時計を差し替えるテストは、時計を「描いたとき」と「描いた面を窓の面へ貼ったとき」
だけ進める。こうすると、機械と負荷によらず、どの列にどの値が出るかが決まる。
"""

import json
import subprocess
from typing import Any

import pytest

from .runner import SKIP_PREBUILD, report_of, run_patched

# 実時間・CPU の時間・眠り・負荷を差し替える。時計は、描いたとき（DRAW_MS ミリ秒。
# CPU の時間はその半分）と、描いた面を窓の面へ貼ったとき（1 ms）だけ進む。窓の面への
# 貼りと眠りは記録して、最後に標準エラーへ JSON の1行で出す。
CLOCKED = """
import json
import pygame
clock = {"wall": 0.0, "cpu": 0.0}
sleeps = []
loads = iter([(1.0, 1.0, 1.0), (2.0, 2.0, 2.0)])
bench_render.time.perf_counter = lambda: clock["wall"]
bench_render.time.thread_time = lambda: clock["cpu"]
def sleep(seconds):
    sleeps.append(seconds)
    clock["wall"] += seconds
bench_render.time.sleep = sleep
bench_render.os.getloadavg = lambda: next(loads)
draw = bench_render.MatchScene.draw
def timed_draw(self, target, frame):
    draw(self, target, frame)
    ms = DRAW_MS(frame)
    clock["wall"] += ms / 1000
    clock["cpu"] += ms / 2000
bench_render.MatchScene.draw = timed_draw
presented = []
class Window(pygame.Surface):
    def blit(self, source, dest, *rest, **kwargs):
        if source is pygame.display.get_surface():
            presented.append([list(source.get_size()), self.get_masks()[3]])
            clock["wall"] += 0.001
        return super().blit(source, dest, *rest, **kwargs)
pygame.Surface = Window
bench_render.main(ARGV)
print(json.dumps({"presented": presented, "sleeps": sleeps}), file=sys.stderr)
"""

# 前の 2 フレーム（捨てる分）は 500 ms。捨て損ねると最大と平均が跳ねる。測る
# 100 フレームは 1〜100 ms を並べ替えた順（37 と 100 は互いに素なので、1 つずつ
# 全部出る）。窓の面への貼りで 1 ms 足すので、実時間は 2〜101 ms が 1 つずつになり、
# 列ごとに値が違う。
SHUFFLED = "500 if frame < 2 else (frame - 2) * 37 % 100 + 1"
GATE_ARGV = ["--tiles", "60", "--frames", "100", "--warmup", "2"]
# SHUFFLED で測ったときの、各列の値。CPU の時間は描く時間の半分（窓の面への貼りは
# 入れていない）。超えは 17〜101 ms の 85 フレーム。
SHUFFLED_STATS = {
    "mean_ms": 51.5,
    "p50_ms": 51.0,
    "p95_ms": 96.0,
    "p99_ms": 100.0,
    "max_ms": 101.0,
    "cpu_p99_ms": 49.5,
}


def run_clocked(draw_ms: str, argv: list[str]) -> subprocess.CompletedProcess[str]:
    """時計を差し替えて測定を走らせる。`draw_ms` は、frame からミリ秒を出す式。"""
    code = CLOCKED.replace("DRAW_MS", f"(lambda frame: {draw_ms})")
    return run_patched(SKIP_PREBUILD + code.replace("ARGV", repr(argv)))


def side_record(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    """標準エラーの最後の行に出した、窓の面への貼りと眠りの記録を読む。"""
    record: dict[str, Any] = json.loads(completed.stderr.strip().splitlines()[-1])
    return record


class TestClocked:
    def test_JSONに_描くことと窓の面への貼りを測った値と_負荷が出る(self) -> None:
        """測る範囲から描くことか窓の面への貼りが抜けると、ほぼ必ず合格と出る。

        まとめ方の取り違え（並べ替えない・CPU の時間の代わりに実時間を入れる・捨てる
        フレームも入れる）も、列の値が変わるので見つかる。窓の面への貼りは、捨てる
        フレームも含めて毎フレーム 1 回、描いた面と同じ大きさで、アルファの桁のある
        面へ（合否はこの形で測って決めた）。全速では眠らない。
        """
        completed = run_clocked(SHUFFLED, [*GATE_ARGV, "--json"])
        report = report_of(completed)
        kinds = [result["particle_kind"] for result in report["results"]]
        assert kinds == ["square", "glow"]
        for result in report["results"]:
            stats = result["stats"]
            seen = {key: stats[key] for key in SHUFFLED_STATS}
            assert seen == pytest.approx(SHUFFLED_STATS)
            assert stats["over_frame"] == 85
        assert report["gate_passed"] is False
        assert report["load_before"] == [1.0, 1.0, 1.0]
        assert report["load_after"] == [2.0, 2.0, 2.0]
        record = side_record(completed)
        # 描いた面は、マス 60 の盤面（1454×1094）・すき間 16・横の板 238 の窓の大きさ。
        assert record["presented"] == [[[1708, 1094], 0xFF000000]] * (2 * 102)
        assert record["sleeps"] == []

    def test_表に_列ごとの値と_負荷と_条件が出る(self) -> None:
        """README の表の値は、この表から書き写す。

        列の入れ違い・行の名前の取り違え・負荷の前後の入れ違いが無いこと。
        """
        completed = run_clocked(SHUFFLED, GATE_ARGV)
        assert completed.returncode == 0, completed.stderr
        lines = completed.stdout.strip().splitlines()
        assert lines[0].startswith("測った時刻：")
        assert lines[2].endswith("測る前 [1.0, 1.0, 1.0] → 後 [2.0, 2.0, 2.0]")
        assert lines[3] == (
            "100 フレームを測った（前の 2 フレームは捨てた）・爆風の位相 そろえる"
            "・薄れる絵 薄めた絵を先に作っておく・全速"
        )
        # split は全角の空白でも区切る（粒子の名前は全角の空白で揃えてある）。
        rows = [line.split() for line in lines if line.startswith("  60  ")]
        values = ["0.0", "51.50", "51.00", "96.00", "100.00", "101.00", "49.50", "85"]
        assert rows == [
            ["60", "1708x1094", "四角い粒", *values],
            ["60", "1708x1094", "光の玉", *values],
        ]
        assert "p99 100.00 ms" in lines[-1]
        assert "→ 不合格" in lines[-1]

    def test_眠りながら回すと_60Hzに合わせて眠り_眠った時間は測らない(self) -> None:
        """README に載せた「眠りながら回した回」の値が、決めた測り方で出ていること。

        眠る長さは、前のフレームの始まりから 1/60 秒経つまで。最初は、測り始めから
        時計が進んでいないので 1/60 秒まるごと眠る。あとは、前のフレームにかかった
        5 ms（描く 4 ms と窓の面への貼り 1 ms）を引いた分だけ眠る。眠った時間が
        測る範囲に入ると、p99 が 5 ms より大きくなる。
        """
        argv = ["--tiles", "26", "--kinds", "glow", "--frames", "5", "--warmup", "1"]
        completed = run_clocked("4", [*argv, "--pace", "sleep", "--json"])
        [result] = report_of(completed)["results"]
        assert result["stats"]["p99_ms"] == pytest.approx(5.0)
        sleeps = side_record(completed)["sleeps"]
        assert sleeps == pytest.approx([1 / 60] + [1 / 60 - 0.005] * 5)


class TestEdgeCases:
    def test_既定の引数で_判定に使う行を測る(self) -> None:
        """案内しているコマンド（引数なし）が、合否を出さずに終わらないこと。"""
        completed = run_patched(
            "from bench_gate import GATE_FADE, GATE_KINDS, GATE_PACE, GATE_PHASES\n"
            "from bench_gate import GATE_TILE, MIN_GATE_FRAMES\n"
            "a = bench_render.parse_args([])\n"
            "print(GATE_TILE in a.tiles, set(GATE_KINDS) <= set(a.kinds),\n"
            "      a.phases == GATE_PHASES, a.fade == GATE_FADE,\n"
            "      a.pace == GATE_PACE, a.frames >= MIN_GATE_FRAMES)\n"
        )
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.split() == ["True"] * 6

    def test_フレームが少ないと_表の最後にそう出す(self) -> None:
        """試し走り（数フレーム）では、フレームが少ないことを先に出すこと。

        この引数では判定に使う行もそろっていないが、理由はフレームの数のほうを出す。
        """
        completed = run_patched(
            SKIP_PREBUILD + "sys.exit(bench_render.main(['--tiles', '60',"
            " '--kinds', 'glow',"
            " '--frames', '3', '--warmup', '1']))\n"
        )
        assert completed.returncode == 0, completed.stderr
        last = completed.stdout.strip().splitlines()[-1]
        assert last == "フレームが 100 より少ないので、合否は出さない"

    def test_負荷を取れないOSでも_負荷を空にして測る(self) -> None:
        """os.getloadavg の無い OS で、負荷を取ろうとして止まらないこと。"""
        completed = run_patched(
            "del bench_render.os.getloadavg\n"
            "sys.exit(bench_render.main(['--tiles', '26', '--kinds', 'glow',"
            " '--frames', '3', '--warmup', '1', '--json']))\n"
        )
        report = report_of(completed)
        assert report["load_before"] is None
        assert report["load_after"] is None
