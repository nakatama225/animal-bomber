"""待ち方の測定（`tools/bench_pacing.py`）が、窓を開かずに走ることの検査。

測った値は機械と負荷で変わるので見ない。見るのは、窓を開かないこと（SDL の dummy
ドライバで描くこと）と、全部の待ち方を測って決めた形で返すこと。別のプロセスで、
3 フレームずつだけ走らせる（`runner.py`）。決め方の計算は `test_bench_pacing_rule.py`。
"""

import itertools
import os

from .runner import report_of, run_pacing, run_patched


class TestBenchPacing:
    def test_窓を開かずに_全部の待ち方を測ってJSONで返す(self) -> None:
        report = report_of(run_pacing())
        assert report["driver"] == "dummy"
        assert (report["tile"], report["particle_kind"]) == (60, "glow")
        [run] = report["runs"]
        names = [stats["candidate"] for stats in run["stats"]]
        assert names == ["sleep", "spin", "sleep_then_spin", "pygame"]
        for stats in run["stats"]:
            assert stats["frames"] == 3
            assert 0 <= stats["draw_p50_ms"] <= stats["draw_p99_ms"]
            assert stats["cpu_share"] > 0
        # 名前と待ち方の取り違えを見つける。空回りは待つ間も CPU を使い続けるので、
        # 眠る待ち方より使用率が高い（3 フレームでも、眠る形は 3 割ほど・空回りは
        # ほぼ 10 割）。
        share = {stats["candidate"]: stats["cpu_share"] for stats in run["stats"]}
        assert share["spin"] > share["sleep"] + 0.2, share
        # 回が 3 回より少なく、フレームも少ないので、選ばない。
        assert report["choice"] is None

    def test_区切りを1周するごとに_周の中で測る位置が変わる(self) -> None:
        """時間とともに変わる機械の状態が、周の中のいつも同じ位置の待ち方に偏らないこと。

        区切りを測る関数を、待ち方の名前を記録するだけのものに差し替えて、3 周させる。
        どの待ち方も、周ごとに違う位置で測られ、2 周続けて先頭にならないことを見る。
        隣り合う組（どの待ち方のすぐあとに測るか）はそろえていない（`bench_pacing.py`
        の「並べ方」）。
        """
        completed = run_patched(
            "order = []\n"
            "bench_pacing.measure_block = lambda name, *rest: order.append(name)\n"
            "bench_pacing.summarize = lambda *args: None\n"
            "bench_pacing.measure_run(None, None, 3, 0, 0)\n"
            "print(' '.join(order))\n"
        )
        assert completed.returncode == 0, completed.stderr
        names = completed.stdout.split()
        rounds = [names[i : i + 4] for i in range(0, len(names), 4)]
        assert len(rounds) == 3
        assert all(sorted(r) == sorted(rounds[0]) for r in rounds)
        for name in rounds[0]:
            positions = [r.index(name) for r in rounds]
            assert len(set(positions)) == len(rounds), (name, positions)
        leads = [r[0] for r in rounds]
        assert all(a != b for a, b in itertools.pairwise(leads)), leads

    def test_環境変数で別のドライバを指定されても_窓を開かない(self) -> None:
        """上書きが外れると SDL の初期化が失敗して、このテストが失敗する。"""
        env = {**os.environ, "SDL_VIDEODRIVER": "no-such-driver"}
        assert report_of(run_pacing(env=env))["driver"] == "dummy"

    def test_dummy以外のドライバで初期化されていたら_set_modeの前に止まる(
        self,
    ) -> None:
        completed = run_patched(
            "bench_pacing.pygame.display.get_driver = lambda: 'cocoa'\n"
            "def opened(*args, **kwargs):\n"
            "    raise AssertionError('set_mode に来た')\n"
            "bench_pacing.pygame.display.set_mode = opened\n"
            "sys.exit(bench_pacing.main(['--runs', '1', '--frames', '3']))\n"
        )
        assert completed.returncode == 1
        assert "dummy 以外のドライバ（cocoa）では測らない" in completed.stderr
        assert "set_mode に来た" not in completed.stderr

    def test_初期化の前に指定が書き換わっていたら_初期化せずに止まる(self) -> None:
        completed = run_patched(
            "os.environ['SDL_VIDEODRIVER'] = 'no-such-driver'\n"
            "sys.exit(bench_pacing.main(['--runs', '1', '--frames', '3']))\n"
        )
        assert completed.returncode == 1
        assert "SDL_VIDEODRIVER が dummy でないので測らない" in completed.stderr
