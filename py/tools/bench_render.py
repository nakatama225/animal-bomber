"""描画の重さを測る（段階 0 の Go/No-Go 判定）。

pygame-ce は描画を CPU で行う。いちばん重い場面の描画がフレームバジェット（60 Hz の
1 フレームに使える時間）に収まらなければ、エンジンを選び直す（退避先は raylib-py）。
それを、絵を描き始める前に、窓を開かずに描いて確かめる。合否は、フレームバジェットの
半分のしきい値（8.33 ms。`bench_gate.py` の `GATE_MS`）で決める。残りの半分は、この
測定に入っていない仕事（下の「測っていないもの」）と、遊ぶ機械が測った機械より古い
ことの分。何をどう描くかは `bench_scene.py`、合格基準と合否の計算は `bench_gate.py`
にある。

## いちばん重い場面

延長戦で盤面がほぼ全部燃えている瞬間を想定する。数は、原型で 4 人とも最強の CPU に
し、延長戦は切ったまま装備を毎フレーム最大にして回した1回で、同時に出ていた数の
最大を、爆風と粒子それぞれで数えたもの（爆風 297 件・粒子 105 個。10800 フレームを
上限に回し、4850 フレームで決着した）。この2つを同じフレームに重ねる。1つの条件で
見た最大なので、上限ではない。爆風は同じマスに重なっても1件ずつ描かれる（原型が
重ねて足しているため）。爆風の位相はそろえる（1回の誘爆で 297 件が出た形）。

粒子は種類で重さが違い、割合は場面で変わる。割合を決め打ちせず、四角い粒だけの行と
光の玉だけの行を両方測り、合否はマス 60 の2行のうち重いほう（p99 の大きいほう）で
決める。回りながら浮かぶ顔（倒れたプレイヤーごとに1個。多くて 4 個）は、どちらにも
105 個の外に足してある。ほかに盤面・背景・プレイヤー 4 人・爆弾 8 個を描く（爆弾の数は
目安）。

薄れる絵（爆風の芯・光の玉）は、貼るたびに薄めるのと同じ整数の不透明度ごとに、薄めた
絵を先に作っておき、薄めずに貼る。描画の層もこの形で書く（`bench_gate.py` の
「直した測り方で測ったあとに決めた」）。貼るたびに `set_alpha` で薄める形は、
`--fade alpha` で参考に測れる。

フレームごとに、描いた面（dummy の画面。アルファの桁の無い XRGB）を、窓の面と
みなした別の面（アルファの桁のある ARGB）へ1回貼る。本物の窓の面の形式は窓を
開かないと分からないので、貼る先を遅いほうの形式にして、その分も測る。

## マスの大きさ

表のマス 37 は TypeScript 版のマス、44 は原型の既定、60 は判定に使う行のマス、96 は
原型が窓に合わせて広げるときの上限（参考）。描画面は、どの行も原型の式で出す（盤面と
まわりの帯がちょうど入る大きさ。マス 37 の行は、TypeScript 版の canvas の 920×680 より
3% 狭い）。60 は、1080p の画面の縦いっぱいに盤面を広げたときの大きさ
（1080 ÷ 18.24 マス ≒ 59px）を上回る（ここまでは測る前に決めた）。Python 版は描く面を
マス 60 までにし、それより大きい窓では描いた面を拡大して出す（レビューで、マスを 96
まで広げるとしきい値を超えると分かったあとに決めた。README の Design Choice）。

## 測っていないもの

- 画面への転送（`pygame.display.flip`）と、大きい窓へ拡大して出す分。窓を開かないので
  測れない
- ルールの計算・音・体力などの文字の表示
- ブロックが壊れたマスの、盤面の絵の描き直し
- アイテム・床に撒かれたもの・宙を飛ぶもの（追いかける炎・跳ね回る爆弾・葱）・
  外周の葱ボン。数が場面で大きく変わるため、ここでは描いていない
- 60 Hz に合わせて眠りながら回したときの遅れ。合否は全速で測って決める
  （`--pace sleep` で参考に測れる）

## 測るとき（合否の決め方）

ほかの重い処理を止めて 3 回走らせる。3 回とも判定に使う値（出力のいちばん下の
「判定：」で始まる行に出る）がしきい値以下なら合格。1 回でも超えたら、ほかの重い処理を
止めて 5 回測り直し、5 回の判定に使う値の中央値で決める。回ごとに、表の頭に出る負荷
（load average）と、測った時刻を残す。負荷があると、1 回だけで不合格になることがある。
しきい値の境目にある描き方は、時間帯（機械の状態）で超えたり下回ったりする
（README の経緯）。

## 使い方

    uv run python tools/bench_render.py          # 表で出す
    uv run python tools/bench_render.py --json   # JSON で出す
    uv run python tools/bench_render.py --tiles 60 --pace sleep
    uv run python tools/bench_render.py --fade alpha      # 貼るたびに薄める形
    uv run python tools/bench_render.py --phases spread   # レビューの前の位相
"""

import argparse
import json
import os
import platform
import random
import sys
import time
from dataclasses import asdict
from typing import Literal

# 窓を開かない。SDL（pygame の下で窓と描画を受け持つライブラリ）は、画面を
# 初期化するときにこの値を読む。環境に実際の窓を開くドライバの名前が入って
# いても窓を開かないよう、上書きする。もう1つは、import したときの挨拶の行を消す。
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame  # noqa: E402 — 上の2つを、pygame を読み込む前に決めるため

from bench_gate import GATE_MS, gate_passed  # noqa: E402
from bench_particles import ParticleKind  # noqa: E402
from bench_report import print_table  # noqa: E402
from bench_result import Result, summarize  # noqa: E402
from bench_scene import PhaseMode, Scene, SceneSpec  # noqa: E402
from bench_sprites import FadeMode  # noqa: E402

Pace = Literal["none", "sleep"]


def measure(spec: SceneSpec, frames: int, warmup: int, seed: int, pace: Pace) -> Result:
    """`warmup` フレーム描いて捨ててから、`frames` フレームの描画時間を測る。

    1 フレームは、場面を描き、描いた面を窓の面とみなした面へ1回貼るまで。
    最初の数フレームを捨てるのは、そこだけ遅いため（読み込みと、メモリの確保）。
    `pace` が "sleep" なら、各フレームの前に、前のフレームの始まりから 1/60 秒
    経つまで眠る（pygame の `Clock.tick(60)` と同じ待ち方。眠った時間は測らない）。
    """
    screen = pygame.display.set_mode(spec.size)
    window = pygame.Surface(spec.size, pygame.SRCALPHA, 32)
    started = time.perf_counter()
    scene = Scene(spec, random.Random(seed))
    setup_ms = (time.perf_counter() - started) * 1000
    wall_ms: list[float] = []
    cpu_ms: list[float] = []
    previous = time.perf_counter()
    for frame in range(warmup + frames):
        if pace == "sleep":
            delay = 1 / 60 - (time.perf_counter() - previous)
            if delay > 0:
                time.sleep(delay)
            previous = time.perf_counter()
        wall_start, cpu_start = time.perf_counter(), time.thread_time()
        scene.draw(screen, frame)
        window.blit(screen, (0, 0))
        if frame >= warmup:
            wall_ms.append((time.perf_counter() - wall_start) * 1000)
            cpu_ms.append((time.thread_time() - cpu_start) * 1000)
    width, height = spec.size
    counts = scene.counts
    return Result(
        tile=spec.tile,
        width=width,
        height=height,
        particle_kind=spec.particle_kind,
        phases=spec.phases,
        blast_phases=scene.blast_phases,
        fade=spec.fade,
        pace=pace,
        blasts=counts["blasts"],
        particles=counts["particles"],
        spinners=counts["spinners"],
        players=counts["players"],
        bombs=counts["bombs"],
        frames=frames,
        setup_ms=setup_ms,
        stats=summarize(wall_ms, cpu_ms),
    )


def load_average() -> list[float] | None:
    """直近 1・5・15 分の負荷（load average）。取れない OS では None。"""
    getloadavg = getattr(os, "getloadavg", None)
    if getloadavg is None:
        return None
    return [round(value, 2) for value in getloadavg()]


def environment() -> dict[str, str]:
    """測った環境（版と描画のドライバ）。結果を読む人が、同じ条件か確かめるため。"""
    sdl = ".".join(str(part) for part in pygame.get_sdl_version())
    return {
        "pygame": pygame.version.ver,
        "sdl": sdl,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "driver": pygame.display.get_driver(),
    }


def positive(text: str) -> int:
    """引数の値を 1 以上の整数として読む。0 以下は既定値に丸めず、誤りにする。"""
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"1 以上にする: {value}")
    return value


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """コマンドラインの引数を読む。既定は、判定に使う行を含む表の全部の行。"""
    parser = argparse.ArgumentParser(description="描画の重さを測る（窓は開かない）")
    parser.add_argument(
        "--tiles", type=positive, nargs="+", default=[37, 44, 52, 60, 96]
    )
    parser.add_argument(
        "--kinds", choices=["square", "glow"], nargs="+", default=["square", "glow"]
    )
    parser.add_argument("--phases", choices=["sync", "spread"], default="sync")
    parser.add_argument("--fade", choices=["baked", "alpha"], default="baked")
    parser.add_argument("--pace", choices=["none", "sleep"], default="none")
    parser.add_argument("--frames", type=positive, default=600)
    parser.add_argument("--warmup", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20261001)
    parser.add_argument("--json", action="store_true", help="結果を JSON で出す")
    args = parser.parse_args(argv)
    if args.warmup < 0:
        parser.error(f"--warmup は 0 以上にする: {args.warmup}")
    return args


def main(argv: list[str] | None = None) -> int:
    """測って結果を出す。合否にかかわらず 0 を返す（合否は出力の中で読む）。"""
    args = parse_args(argv)
    # 上の上書きのあとで、ほかのコードが値を変えていたら、初期化の前に止める。
    if os.environ.get("SDL_VIDEODRIVER") != "dummy":
        raise SystemExit("SDL_VIDEODRIVER が dummy でないので測らない")
    before = load_average()
    pygame.display.init()
    try:
        driver = pygame.display.get_driver()
        if driver != "dummy":
            # ここまで来るのは、先にほかのコードが別のドライバで画面を初期化して
            # いたとき。窓を開く（set_mode）前に止める。
            raise SystemExit(f"dummy 以外のドライバ（{driver}）では測らない")
        kinds: list[ParticleKind] = args.kinds
        phases: PhaseMode = args.phases
        fade: FadeMode = args.fade
        results = [
            measure(
                SceneSpec(tile, kind, phases, fade),
                args.frames,
                args.warmup,
                args.seed,
                args.pace,
            )
            for tile in args.tiles
            for kind in kinds
        ]
        after = load_average()
        if args.json:
            report = {
                **environment(),
                "load_before": before,
                "load_after": after,
                "frames": args.frames,
                "warmup": args.warmup,
                "phases": args.phases,
                "fade": args.fade,
                "pace": args.pace,
                "gate_ms": GATE_MS,
                "gate_passed": gate_passed(results, args.frames),
                "results": [asdict(result) for result in results],
            }
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print_table(results, args, environment(), (before, after))
    finally:
        pygame.display.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
