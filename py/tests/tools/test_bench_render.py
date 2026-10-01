"""描画の重さの測定（`tools/bench_render.py`）が、窓を開かずに走ることの検査。

測った値は機械と、そのときの負荷で変わるので、ここでは見ない。見るのは、
窓を開かないこと（SDL の dummy ドライバで描くこと）と、結果を決めた形で返すこと。
測定は開発のたびには走らせないので、壊れていても気づきにくい。

どれも別のプロセスで走らせる（このプロセスで pygame の画面を初期化しないため。
`runner.py`）。ほとんどは小さな場面を数フレームだけ描く。判定に使う行を確かめる
ものだけは、マス 60 を 100 フレーム描く。合わせて数秒で終わる。測る範囲と列の値は
`test_bench_measure.py`、描き方の数は `test_bench_scene.py` が確かめる。
"""

import os

import pytest

from .runner import report_of, run_bench, run_patched


class TestBenchRender:
    def test_窓を開かずに描いて_結果をJSONで返す(self) -> None:
        """測定が、壊れたまま次に使うときまで放置されないためのもの。

        場面が持っている数（描くはずの数）も見る。数を減らして場面を軽くしても、
        時間の値だけを見ていると気づけない。実際に描いた回数は JSON に出ないので、
        `test_bench_scene.py` が描く先の面で数える。
        """
        report = report_of(run_bench("--tiles", "26", "--kinds", "glow"))
        assert report["driver"] == "dummy"
        [result] = report["results"]
        assert (result["tile"], result["particle_kind"]) == (26, "glow")
        assert (result["phases"], result["fade"], result["pace"]) == (
            "sync",
            "baked",
            "none",
        )
        assert (result["width"], result["height"]) == (630, 474)
        counts = [result[key] for key in ("blasts", "particles", "spinners")]
        assert counts + [result["players"], result["bombs"]] == [297, 105, 4, 4, 8]
        # 位相をそろえ損ねると、薄れた絵をまとめて貼るフレームが無くなり、軽く測れる。
        assert result["blast_phases"] == 1
        stats = result["stats"]
        assert 0 <= stats["p50_ms"] <= stats["p99_ms"] <= stats["max_ms"]
        assert stats["cpu_p99_ms"] >= 0 and stats["over_frame"] >= 0
        # フレームが 100 より少ないうえ、判定に使う行（マス 60 の四角い粒と光の玉）も
        # 測っていないので、合否は出さない（フレームの数の確かめが先に効く）。
        assert report["gate_passed"] is None

    def test_判定に使う行を測ると_合否を出す(self) -> None:
        """判定に使う行を見つけ損ねて、測ったのに合否が出ない（None）事故を防ぐ。

        別の行で合否を出すずれは、`test_bench_gate.py` が値で確かめる。
        合否そのものは機械と負荷で変わるので、ここでは見ない。
        """
        completed = run_bench("--tiles", "60", "--frames", "100")
        assert report_of(completed)["gate_passed"] in (True, False)

    def test_フレームが少ないと_合否を出さない(self) -> None:
        """数フレームだけの試し走りを、合否が出たと読み違えないこと。

        100 フレームより少ないと、99 パーセンタイルが最大と同じ値になる。
        """
        report = report_of(run_bench("--tiles", "60"))
        assert report["frames"] == 3
        assert report["gate_passed"] is None

    @pytest.mark.parametrize(
        ("step", "verdict", "p99"),
        [(0.004, "→ 合格", "4.00"), (0.009, "→ 不合格", "9.00")],
    )
    def test_表で出すと_最後の行に合否を出す(
        self, step: float, verdict: str, p99: str
    ) -> None:
        """案内しているのは表で出す使い方なので、表の側も壊れていないこと。

        時計を「呼ぶたびに決まった秒だけ進む」ものに差し替え、どのフレームも同じ
        時間にする。合否の文字の取り違えと、秒とミリ秒の取り違えを見つける。
        """
        completed = run_patched(
            "ticks = itertools.count()\n"
            f"bench_render.time.perf_counter = lambda: next(ticks) * {step}\n"
            "sys.exit(bench_render.main(['--tiles', '60', '--frames', '100',"
            " '--warmup', '0']))\n"
        )
        assert completed.returncode == 0, completed.stderr
        lines = completed.stdout.strip().splitlines()
        assert verdict in lines[-1]
        assert f"p99 {p99} ms" in lines[-1]
        rows = [line for line in lines if line.startswith("  60  ")]
        # マス・大きさ・粒子・準備・平均・p50・p95 の次が p99。
        # split は全角の空白でも区切る。
        assert [row.split()[7] for row in rows] == [p99, p99]

    def test_環境変数で別のドライバを指定されても_窓を開かない(self) -> None:
        """環境に実際の窓を開くドライバの名前が入っていても、dummy で描くこと。

        存在しない名前を入れて確かめる。上書きが外れると SDL の初期化が失敗して、
        このテストが失敗する。実在するドライバの名前で確かめると、上書きが外れた
        ときに本当に窓が開いてしまう。
        """
        env = {**os.environ, "SDL_VIDEODRIVER": "no-such-driver"}
        report = report_of(run_bench("--tiles", "26", "--kinds", "square", env=env))
        assert report["driver"] == "dummy"

    def test_初期化の前に指定が書き換わっていたら_初期化せずに止まる(self) -> None:
        """上書きのあとで、ほかのコードが指定を変えていたときの止め。"""
        completed = run_patched(
            "os.environ['SDL_VIDEODRIVER'] = 'no-such-driver'\n"
            "sys.exit(bench_render.main(['--tiles', '26', '--frames', '3']))\n"
        )
        assert completed.returncode == 1
        assert "SDL_VIDEODRIVER が dummy でないので測らない" in completed.stderr

    def test_dummy以外のドライバで初期化されていたら_set_modeの前に止まる(
        self,
    ) -> None:
        """先にほかのコードが別のドライバで画面を初期化していたときの止め。

        ドライバの名前を偽るだけで、SDL は dummy のまま初期化される。窓を開く
        `set_mode` は、呼ばれたら失敗するものに差し替えてある。
        """
        completed = run_patched(
            "bench_render.pygame.display.get_driver = lambda: 'cocoa'\n"
            "def opened(*args, **kwargs):\n"
            "    raise AssertionError('set_mode に来た')\n"
            "bench_render.pygame.display.set_mode = opened\n"
            "sys.exit(bench_render.main(['--tiles', '26', '--frames', '3']))\n"
        )
        assert completed.returncode == 1
        assert "dummy 以外のドライバ（cocoa）では測らない" in completed.stderr
        assert "set_mode に来た" not in completed.stderr

    def test_薄めた絵を先に作っても_1枚ごとの見た目は貼るたびに薄めるのと同じ(
        self,
    ) -> None:
        """薄れる絵を先に作っておく形（fade が baked）が、見た目を変えないこと。

        爆風1件・光の玉1個だけの場面を、同じ乱数で、貼るたびに薄める形と先に作って
        おく形で 60 フレームずつ描き（爆風の 28 刻みと光の玉の寿命の 30 刻みを1周以上
        通る）、画面の全部の画素で色の差が 2 以下かを見る。絵の選び方（どの不透明度の
        写しを貼るか）まで通して確かめる。不透明度を粗い段に丸めると、差が 5 まで出た。

        1枚ごとの差は丸めの違い（貼るときに薄めるのと、写しを作るときの計算の違い）で、
        この機械では 1 だった。何枚も重なる所では足し合わさり、全部を描く場面では
        最大 6 になった（255 段のうち。README に書いてある）。

        差は2つの面の引き算（BLEND_RGB_SUB は 0 で切れるので、両方の向きで引く）で
        作り、黒から 3 未満の画素を数える。
        """
        completed = run_patched(
            "import random\n"
            "import pygame\n"
            "from bench_scene import Scene, SceneSpec\n"
            "pygame.display.init()\n"
            "pygame.display.set_mode((630, 474))\n"
            "few = {'particles': 1, 'spinners': 0, 'blasts': 1,\n"
            "       'players': 0, 'bombs': 0}\n"
            "def scene(fade):\n"
            "    spec = SceneSpec(26, 'glow', fade=fade, **few)\n"
            "    return Scene(spec, random.Random(7))\n"
            "by_alpha, baked = scene('alpha'), scene('baked')\n"
            "a = pygame.Surface((630, 474)).convert()\n"
            "b = pygame.Surface((630, 474)).convert()\n"
            "outside = 0\n"
            "for frame in range(60):\n"
            "    by_alpha.draw(a, frame)\n"
            "    baked.draw(b, frame)\n"
            "    for x, y in ((a, b), (b, a)):\n"
            "        diff = x.copy()\n"
            "        diff.blit(y, (0, 0), special_flags=pygame.BLEND_RGB_SUB)\n"
            "        near = pygame.mask.from_threshold(\n"
            "            diff, (0, 0, 0), (3, 3, 3, 255))\n"
            "        outside += 630 * 474 - near.count()\n"
            "print(outside)\n"
        )
        assert completed.returncode == 0, completed.stderr
        assert int(completed.stdout.strip()) == 0

    @pytest.mark.parametrize(
        ("args", "message"),
        [
            (("--frames", "0"), "1 以上にする"),
            (("--tiles", "0"), "1 以上にする"),
            (("--warmup", "-1"), "0 以上にする"),
        ],
    )
    def test_範囲の外の引数なら_測らずに失敗する(
        self, args: tuple[str, str], message: str
    ) -> None:
        """0 フレームを「測った」ことにしたり、大きさ 0 の面で黙って測ったりしないこと。

        大きさ 0 の面を頼むと、pygame は別の大きさの面を作って、そのまま測り終える。
        """
        completed = run_bench("--tiles", "26", *args)
        assert completed.returncode == 2
        assert message in completed.stderr
