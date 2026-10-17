"""描画の層の取っておいた絵を通して、いちばん重い場面の描画時間を測る。

`bench_render.py`（段階 0 の判定）は、描画の層を作る前に、代わりの絵で場面を描いて
測った。こちらは、原型の描く関数を写した描画の層（`presentation/render/`）が描いて
取っておいた絵を貼る形で、同じ場面（と、プレイヤー・爆弾・アイテム）を描く
（`bench_art_scene.py`）。絵を全部写す前に、この形で間に合うかを確かめるためのもの。

測り方と合否の決め方は `bench_render.py` と同じ（窓を開かない・600 フレームを全速で
描き、1 フレームは場面を描いて窓の面とみなした面へ1回貼るまで・合格基準は
`bench_gate.py`）。ほかの重い処理を止めて 3 回走らせ、3 回とも「判定：」の行の値が
しきい値（8.33 ms）以下なら合格。回ごとに、表の頭に出る負荷（load average）と時刻を
残す。

`--first-draw` を付けると、取っておく絵を初めて描くときの時間（まだ取っていない姿が
初めて出たフレームの遅れ）を、絵の種類ごとに測って出す。

## 使い方

    uv run python tools/bench_art.py                 # マス 60 の2行（判定に使う行）
    uv run python tools/bench_art.py --tiles 44 60
    uv run python tools/bench_art.py --first-draw
"""

import argparse
import json
import os
import random
import sys
import time
from dataclasses import asdict
from datetime import datetime
from typing import Any

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame  # noqa: E402 — 上の2つを、pygame を読み込む前に決めるため

from bench_art_scene import ArtScene, ArtSceneSpec  # noqa: E402
from bench_first_draw import first_draw_times  # noqa: E402
from bench_gate import GATE_MS, gate_passed  # noqa: E402
from bench_particles import ParticleKind  # noqa: E402
from bench_render import environment, load_average, positive  # noqa: E402
from bench_report import print_table  # noqa: E402
from bench_result import Result, summarize  # noqa: E402


def measure(spec: ArtSceneSpec, frames: int, warmup: int, seed: int) -> Result:
    """`warmup` フレーム描いて捨ててから、`frames` フレームの描画時間を測る。

    1 フレームは、場面を描き、描いた面を窓の面とみなした面（アルファの桁のある面）へ
    1回貼るまで（`bench_render.py` と同じ）。準備（取っておく絵を先に描く分を含む）の
    時間は `setup_ms` に入る。
    """
    screen = pygame.display.set_mode(spec.size)
    window = pygame.Surface(spec.size, pygame.SRCALPHA, 32)
    started = time.perf_counter()
    scene = ArtScene(spec, random.Random(seed))
    setup_ms = (time.perf_counter() - started) * 1000
    wall_ms: list[float] = []
    cpu_ms: list[float] = []
    for frame in range(warmup + frames):
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
        f"・アイテム {counts['items']} 個"
        f"・測る間に描いた絵 {scene.renders - scene.cached_sprites} 枚",
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
        pace="none",
        blasts=counts["blasts"],
        particles=counts["particles"],
        spinners=counts["spinners"],
        players=counts["players"],
        bombs=counts["bombs"],
        frames=frames,
        setup_ms=setup_ms,
        stats=summarize(wall_ms, cpu_ms),
    )


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """コマンドラインの引数を読む。既定は判定に使う2行（マス 60 の2種類の粒子）。"""
    parser = argparse.ArgumentParser(description="描画の層を通して描画の重さを測る")
    parser.add_argument("--tiles", type=positive, nargs="+", default=[60])
    parser.add_argument(
        "--kinds", choices=["square", "glow"], nargs="+", default=["square", "glow"]
    )
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
    # 表の頭の行（bench_report.print_table）が読む、測り方の値。この測定では変えない。
    args.phases, args.fade, args.pace = "sync", "baked", "none"
    return args


def main(argv: list[str] | None = None) -> int:
    """測って結果を出す。合否にかかわらず 0 を返す（合否は出力の中で読む）。"""
    args = parse_args(argv)
    if os.environ.get("SDL_VIDEODRIVER") != "dummy":
        raise SystemExit("SDL_VIDEODRIVER が dummy でないので測らない")
    before = load_average()
    measured_at = datetime.now().astimezone().isoformat(timespec="seconds")
    pygame.display.init()
    pygame.font.init()
    try:
        driver = pygame.display.get_driver()
        if driver != "dummy":
            raise SystemExit(f"dummy 以外のドライバ（{driver}）では測らない")
        if args.first_draw:
            times = {tile: first_draw_times(tile) for tile in args.tiles}
            print(json.dumps({"tiles": times}, ensure_ascii=False, indent=2))
            return 0
        kinds: list[ParticleKind] = args.kinds
        results = [
            measure(ArtSceneSpec(tile, kind), args.frames, args.warmup, args.seed)
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
