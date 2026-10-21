"""描画の重さを測る（本物の描画の層 `Renderer` で、いちばん重い場面を描く）。

pygame-ce は描画を CPU で行う。いちばん重い場面の描画が、フレームバジェット（60 Hz の
1 フレームに使える時間）の半分のしきい値（8.33 ms。`bench_gate.py` の `GATE_MS`）に
収まるかを、窓を開かずに描いて確かめる。残りの半分は、この測定に入っていない仕事
（下の「測っていないもの」）と、遊ぶ機械が測った機械より古いことの分。何をどう描くかは
`bench_match_scene.py`、合格基準と合否の計算は `bench_gate.py` にある。

段階 0 では、描画の層を作る前に、代わりの絵で同じ数の場面を描いて測り、pygame-ce で
作り進めるかを決めた（`bench_scene.py`。README の Design Choice 1. の経緯）。段階 7 で
描画の層ができたので、その層を通して描く形に替えた（合格基準は変えていない）。

## いちばん重い場面

延長戦で盤面がほぼ全部燃えている瞬間を想定する。数は、原型で 4 人とも最強の CPU に
し、延長戦は切ったまま装備を毎フレーム最大にして回した1回で、同時に出ていた数の
最大を、爆風と粒子それぞれで数えたもの（爆風 297 件・粒子 105 個。10800 フレームを
上限に回し、4850 フレームで決着した）。この2つを同じフレームに重ねる。1つの条件で
見た最大なので、上限ではない。爆風は同じマスに重なっても1件ずつ描かれる（原型が
重ねて足しているため）。爆風の位相はそろえる（1回の誘爆で 297 件が出た形）。

粒子は種類で重さが違い、割合は場面で変わる。割合を決め打ちせず、四角い粒だけの行と
光の玉（追いかける炎の通った跡）だけの行を両方測り、合否はマス 60 の2行のうち重いほう
（p99 の大きいほう）で決める。回りながら浮かぶ顔（倒れたプレイヤーごとに1個。多くて
4 個）は、どちらにも 105 個の外に足してある。ほかに、4 匹の違う動物（技の絵と状態の印
つき）・爆弾 8 個・アイテム 20 個・粘膜爆弾・追いかける炎を描き、画面はいつも揺らす
（数は目安）。段階 10 から、盤面の右の横の板（時計の数字の明滅と、名札の中身が変わった
ときの作り直し）も描く。

フレームごとに、描いた面（dummy の画面。アルファの桁の無い XRGB）を、窓の面と
みなした別の面（アルファの桁のある ARGB）へ1回貼る。本物の窓の面の形式は窓を
開かないと分からないので、貼る先を遅いほうの形式にして、その分も測る。

## マスの大きさ

表のマス 37 は TypeScript 版のマス、44 は原型の既定、60 は判定に使う行のマス。描く面は
マス 60 までにする（README の Design Choice 1.）。pygame の SCALED は整数倍でしか
広げないので、拡大するのは、画面の縦が描く面の 2 倍以上あるときだけ。それより小さい
画面では、窓は描く面と同じ大きさ（マス 60 で 1454×1126）。原型はマス 96 まで広げるので、
大きい画面では盤面が原型より小さい（2560×1440 相当でマス 60 と 69、3840×2160 を等倍で
使うとき 60 と 96）。整数でない倍率で広げる設定は、実機の窓で見た目と重さを確かめてから
決める。描画面は原型の式で出す（盤面とまわりの帯がちょうど入る大きさ。`Layout`）に、
すき間 16px と横の板 238px を足した窓の大きさ（`bench_match_visuals.py` の `size`）。

## 測っていないもの

- 画面への転送（`pygame.display.flip`）と、画面の縦が描く面の 2 倍以上あるときに整数倍に
  拡大して出す分。窓を開かないので測れない
- ルールの計算・音・見た目だけの値を数える分（`SceneTracker`）・横の板の名札の新しい
  文を初めて描く分（場面では先に描いておく。中身を作る `hud/` の関数は毎フレーム測る）
- ブロックが壊れたときの、盤面を1枚に合わせ直す分（`baked/board.py` の `BoardLayer`）
- 外周の鍋と飛んでいる葱（段階 8）。外周にいるプレイヤーは盤面にいないので、鍋を足すと
  盤面のプレイヤーが減る。測定の場面の2体を外周に回して葱を1本ずつ飛ばした場面は、4体とも
  盤面にいる場面より軽かったので、場面には足していない（README の Design Choice 1.）
- 60 Hz に合わせて眠りながら回したときの遅れ。合否は全速で測って決める
  （`--pace sleep` で参考に測れる）

## 測るとき（合否の決め方）

ほかの重い処理を止めて 3 回走らせる。3 回とも判定に使う値（出力のいちばん下の
「判定：」で始まる行に出る）がしきい値以下なら合格。1 回でも超えたら、ほかの重い処理を
止めて 5 回測り直し、5 回の判定に使う値の中央値で決める。回ごとに、表の頭に出る負荷
（load average）と、測った時刻を残す。

`--first-draw` を付けると、取っておく絵を初めて描くときの時間（まだ取っていない姿が
初めて出たフレームの遅れ）と、試合の前に描いておく時間を、絵の種類ごとに測って出す
（`bench_first_draw.py`）。

## 使い方

    uv run python tools/bench_render.py          # 表で出す
    uv run python tools/bench_render.py --json   # JSON で出す
    uv run python tools/bench_render.py --tiles 60 --pace sleep
    uv run python tools/bench_render.py --first-draw
"""

import argparse
import json
import os
import platform
import random
import sys
import time
from dataclasses import asdict
from datetime import datetime
from typing import Any, Literal

# 窓を開かない。SDL（pygame の下で窓と描画を受け持つライブラリ）は、画面を
# 初期化するときにこの値を読む。環境に実際の窓を開くドライバの名前が入って
# いても窓を開かないよう、上書きする。もう1つは、import したときの挨拶の行を消す。
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame  # noqa: E402 — 上の2つを、pygame を読み込む前に決めるため

from bench_first_draw import first_draw_times  # noqa: E402
from bench_gate import GATE_MS, gate_passed  # noqa: E402
from bench_match_scene import MatchScene  # noqa: E402
from bench_match_visuals import MatchSceneSpec, ParticleKind  # noqa: E402
from bench_report import print_table  # noqa: E402
from bench_result import Result, summarize  # noqa: E402

Pace = Literal["none", "sleep"]


def measure(
    spec: MatchSceneSpec, frames: int, warmup: int, seed: int, pace: Pace
) -> Result:
    """`warmup` フレーム描いて捨ててから、`frames` フレームの描画時間を測る。

    1 フレームは、場面を描き、描いた面を窓の面とみなした面へ1回貼るまで。
    最初の数フレームを捨てるのは、そこだけ遅いため（読み込みと、メモリの確保）。
    `pace` が "sleep" なら、各フレームの前に、前のフレームの始まりから 1/60 秒
    経つまで眠る（pygame の `Clock.tick(60)` と同じ待ち方。眠った時間は測らない）。
    準備（試合の前に絵を描いておく分を含む）の時間は `setup_ms` に入る。
    """
    screen = pygame.display.set_mode(spec.size)
    window = pygame.Surface(spec.size, pygame.SRCALPHA, 32)
    started = time.perf_counter()
    scene = MatchScene(spec, random.Random(seed))
    setup_ms = (time.perf_counter() - started) * 1000
    built = scene.renders
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
    print(
        f"マス {spec.tile} {spec.particle_kind}: 準備 {setup_ms:.0f} ms"
        f"（先に描いた絵 {scene.cached_sprites} 枚・{scene.prebuild_ms:.0f} ms）"
        f"・測る間に描いた絵 {scene.renders - built} 枚",
        file=sys.stderr,
    )
    return Result(
        tile=spec.tile,
        width=width,
        height=height,
        particle_kind=spec.particle_kind,
        phases="sync",
        blast_phases=scene.blast_phases,
        fade="baked",
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


def tile_size(text: str) -> int:
    """マスの大きさとして読む。描く面の寸法（`Layout`）が受け付ける 26〜60 だけ。"""
    value = positive(text)
    if not 26 <= value <= 60:
        raise argparse.ArgumentTypeError(f"マスは 26〜60 にする: {value}")
    return value


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """コマンドラインの引数を読む。既定は、判定に使う行を含む表の全部の行。"""
    parser = argparse.ArgumentParser(description="描画の重さを測る（窓は開かない）")
    parser.add_argument("--tiles", type=tile_size, nargs="+", default=[37, 44, 52, 60])
    parser.add_argument(
        "--kinds", choices=["square", "glow"], nargs="+", default=["square", "glow"]
    )
    parser.add_argument("--pace", choices=["none", "sleep"], default="none")
    parser.add_argument("--frames", type=positive, default=600)
    parser.add_argument("--warmup", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20261018)
    parser.add_argument("--json", action="store_true", help="結果を JSON で出す")
    parser.add_argument(
        "--first-draw", action="store_true", help="絵を初めて描くときの時間を測る"
    )
    args = parser.parse_args(argv)
    if args.warmup < 0:
        parser.error(f"--warmup は 0 以上にする: {args.warmup}")
    # 表の頭の行（bench_report.print_table）と合格基準（bench_gate.py）が読む、測り方の
    # 値。爆風の位相はいつもそろえ、薄れる絵はいつも先に作っておく（描画の層の形）。
    args.phases, args.fade = "sync", "baked"
    return args


def main(argv: list[str] | None = None) -> int:
    """測って結果を出す。合否にかかわらず 0 を返す（合否は出力の中で読む）。"""
    args = parse_args(argv)
    # 上の上書きのあとで、ほかのコードが値を変えていたら、初期化の前に止める。
    if os.environ.get("SDL_VIDEODRIVER") != "dummy":
        raise SystemExit("SDL_VIDEODRIVER が dummy でないので測らない")
    before = load_average()
    measured_at = datetime.now().astimezone().isoformat(timespec="seconds")
    pygame.display.init()
    pygame.font.init()
    try:
        driver = pygame.display.get_driver()
        if driver != "dummy":
            # ここまで来るのは、先にほかのコードが別のドライバで画面を初期化して
            # いたとき。窓を開く（set_mode）前に止める。
            raise SystemExit(f"dummy 以外のドライバ（{driver}）では測らない")
        if args.first_draw:
            times = {tile: first_draw_times(tile) for tile in args.tiles}
            print(json.dumps({"tiles": times}, ensure_ascii=False, indent=2))
            return 0
        kinds: list[ParticleKind] = args.kinds
        results = [
            measure(
                MatchSceneSpec(tile, kind),
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
            report: dict[str, Any] = {
                **environment(),
                "measured_at": measured_at,
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
            print(f"測った時刻：{measured_at}")
            print_table(results, args, environment(), (before, after))
    finally:
        pygame.display.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
