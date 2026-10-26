"""フレームの間の待ち方を比べて測る（段階 1）。決め方は `bench_pacing_rule.py`。

窓は開かない（`bench_render.py` と同じく、SDL の dummy ドライバで描く）。そのため、
画面への転送（`flip`）も、画面の書き換えに合わせて待つ設定（vsync）も測れない。
vsync を使うかは、窓を開く段階で決める（使うなら、輪で待つ必要が無くなる）。

## 何を測るか

本物のフレームを繰り返す輪（`src/animal_bomber/shell/loop.py` の `frames`）を
候補の待ち方で実行し、各フレームで、段階 0 の描画の重さの測定の場面（代わりの絵の
`bench_scene.py`。マス 60・光の玉・位相をそろえる・薄めた絵を先に作る）を描く。試合の
計算はしない（段階 1 では移動だけで軽い）。描画の重さの測定（`bench_render.py`）は、
段階 7 から本物の描画の層で描くが、ここは README の Design Choice 7. の値を測ったときの
場面のままにしてある（場面を替えたら測り直す）。

- 描画時間：場面を描き、描いた面を窓の面とみなした面へ 1 回貼るまで
- 遅れ：待つ関数が返った時刻と、予定の時刻の差（待つ関数を包んで測る）
- 1 tick 以外を進めたフレームの数
- CPU の使用率：その候補を測った間の、このプロセスの CPU 時間 ÷ 実時間

## 並べ方

機械の状態で、同じ描画の時間が 2 倍ほど変わった（描画の重さの測定の 18 時台と
19 時台）。候補を別々の時刻に測ると、その差が候補の差に見える。そこで1回の測定の
中で、候補を短い区切り（既定 200 フレーム）ずつ交互に測り、区切りを1周するごとに
先頭にする候補を1つずつずらす（候補ごとに周の中で測る位置が変わり、時間とともに
変わる機械の状態が、1つの候補に偏らない）。これを3回繰り返し、3回の結果で決める。
区切りごとに輪を作り直し、最初の数フレーム（既定 20）は捨てる。

⚠️ ずらしても、隣り合う組（どの候補のすぐあとにどの候補を測るか）は変わらない。
空回りのすぐあとは、回の切れ目を除いて、いつも眠ってから空回りする形になる（空回りが
機械を温める影響が乗るなら、その候補に乗る）。段階 4 で測り直すときは、隣り合う組も
そろう並べ方（交互に測る待ち方が4つなら4周の、釣り合った Williams の並べ方）に
替える。

## 使い方

    uv run python tools/bench_pacing.py          # 表で出す（3 回。2 分半ほど）
    uv run python tools/bench_pacing.py --json   # JSON で出す
"""

import argparse
import json
import os
import random
import sys
import time
from dataclasses import asdict, dataclass, field

# 窓を開かない（理由は bench_render.py の同じ行）。
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame  # noqa: E402 — 上の2つを、pygame を読み込む前に決めるため

from animal_bomber.shell.loop import (  # noqa: E402
    Clock,
    Wait,
    frames,
    sleep_then_spin,
    sleep_until,
    spin_until,
)
from bench_pacing_rule import (  # noqa: E402
    CANDIDATES,
    REFERENCES,
    Choice,
    PaceStats,
    choose,
    summarize,
    timed,
    violations,
)
from bench_render import environment, load_average, positive  # noqa: E402
from bench_scene import Scene, SceneSpec  # noqa: E402

NAMES = CANDIDATES + REFERENCES
SPEC = SceneSpec(60, "glow")


def make_wait(name: str) -> Wait:
    """候補の名前から待つ関数を作る。pygame の `Clock` は区切りごとに作り直す。"""
    if name == "sleep":
        return sleep_until
    if name == "spin":
        return spin_until
    if name == "sleep_then_spin":
        return sleep_then_spin
    if name == "pygame":
        pygame_clock = pygame.time.Clock()

        def wait(deadline: int, clock: Clock) -> None:
            pygame_clock.tick(60)

        return wait
    raise ValueError(f"知らない待ち方: {name}")


@dataclass
class Samples:
    """1つの待ち方の、1回の測定の中の全部の区切りぶんの値。"""

    draw_ms: list[float] = field(default_factory=list)
    late_ms: list[float] = field(default_factory=list)
    ticks: list[int] = field(default_factory=list)
    cpu_s: float = 0.0
    wall_s: float = 0.0


@dataclass(frozen=True)
class Run:
    """1回の測定の結果。負荷は直近 1・5・15 分の load average（取れなければ None）。"""

    time: str
    load_before: list[float] | None
    load_after: list[float] | None
    stats: list[PaceStats]


def measure_block(
    name: str,
    scene: Scene,
    screens: tuple[pygame.Surface, pygame.Surface],
    first_frame: int,
    frames_n: int,
    warmup: int,
    samples: Samples,
) -> None:
    """1つの区切り：輪を作り、`warmup` フレーム捨ててから `frames_n` フレーム測る。

    測る範囲は、捨てた最後のフレームを描き終えてから、測った最後のフレームを描き
    終えるまで（待ちと描画を `frames_n` 回ずつ含む）。
    """
    screen, window = screens
    late_ns: list[int] = []
    loop = frames(time.perf_counter_ns, timed(make_wait(name), late_ns))
    cpu_start = wall_start = 0.0
    for index, ticks in enumerate(loop):
        measured = index >= warmup
        if measured:
            samples.ticks.append(ticks)
        started = time.perf_counter_ns()
        scene.draw(screen, first_frame + index)
        window.blit(screen, (0, 0))
        if measured:
            samples.draw_ms.append((time.perf_counter_ns() - started) / 1e6)
        if index == warmup - 1:
            cpu_start, wall_start = time.process_time(), time.perf_counter()
        if index == warmup + frames_n - 1:
            break
    samples.cpu_s += time.process_time() - cpu_start
    samples.wall_s += time.perf_counter() - wall_start
    # 最初のフレームは待たないので、i 番目のフレームの前の待ちは late_ns[i - 1]。
    measured_late = late_ns[warmup - 1 : warmup - 1 + frames_n]
    samples.late_ms.extend(ns / 1e6 for ns in measured_late)


def measure_run(
    scene: Scene,
    screens: tuple[pygame.Surface, pygame.Surface],
    rounds: int,
    frames_n: int,
    warmup: int,
) -> list[PaceStats]:
    """1回の測定：全部の待ち方を区切りごとに交互に測り、`rounds` 周する。"""
    samples = {name: Samples() for name in NAMES}
    frame = 0
    for round_index in range(rounds):
        shift = round_index % len(NAMES)
        for name in NAMES[shift:] + NAMES[:shift]:
            measure_block(name, scene, screens, frame, frames_n, warmup, samples[name])
            frame += warmup + frames_n
    return [
        summarize(name, s.draw_ms, s.late_ms, s.ticks, s.cpu_s, s.wall_s)
        for name, s in samples.items()
    ]


def verdict(stats: PaceStats) -> str:
    """表の判定の欄に出す文字。"""
    if stats.candidate in REFERENCES:
        return "参考"
    found = violations(stats)
    if found is None:
        return "フレームが少ない"
    return "不合格：" + "・".join(found) if found else "合格"


def print_table(runs: list[Run], choice: Choice | None, env: dict[str, str]) -> None:
    """結果を表で出す。最後の行が、選んだ待ち方。時間はミリ秒。"""
    print(f"pygame {env['pygame']} / SDL {env['sdl']} / Python {env['python']}")
    print(f"{env['platform']} / ドライバ {env['driver']}")
    head = "  待ち方           描画p50 描画p99 遅れp50 遅れp99 遅れ最大 1tick以外  CPU"
    for number, run in enumerate(runs, 1):
        print(f"\n回 {number}（{run.time}、負荷 {run.load_before} → {run.load_after}）")
        print(head)
        for s in run.stats:
            print(
                f"  {s.candidate:<16} {s.draw_p50_ms:7.2f} {s.draw_p99_ms:7.2f}"
                f" {s.late_p50_ms:7.2f} {s.late_p99_ms:7.2f} {s.late_max_ms:8.2f}"
                f" {s.off_tick:4d}/{s.frames:<4d} {s.cpu_share:5.0%}  {verdict(s)}"
            )
    if choice is None:
        print("\n選んだ待ち方：なし（回が 3 回より少ないか、フレームが少ない）")
        return
    if choice.fallback:
        how = "代わりに選んだ。3 回とも合格した候補が無い"
    else:
        how = "3 回とも合格した候補のうち、CPU の使用率の中央値がいちばん低い"
    print(f"\n選んだ待ち方：{choice.chosen}（{how}）")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """コマンドラインの引数を読む。"""
    parser = argparse.ArgumentParser(description="フレームの間の待ち方を比べて測る")
    parser.add_argument("--runs", type=positive, default=3)
    parser.add_argument(
        "--rounds",
        type=positive,
        default=3,
        help="1回の測定で、全部の待ち方の区切りを何周するか",
    )
    parser.add_argument(
        "--frames", type=positive, default=200, help="1つの区切りで測るフレームの数"
    )
    parser.add_argument(
        "--warmup",
        type=positive,
        default=20,
        help="1つの区切りの初めに捨てるフレームの数",
    )
    parser.add_argument("--seed", type=int, default=20261003)
    parser.add_argument("--json", action="store_true", help="結果を JSON で出す")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """測って結果を出す。"""
    args = parse_args(argv)
    # 上の上書きのあとで、ほかのコードが値を変えていたら、初期化の前に止める。
    if os.environ.get("SDL_VIDEODRIVER") != "dummy":
        raise SystemExit("SDL_VIDEODRIVER が dummy でないので測らない")
    pygame.display.init()
    try:
        driver = pygame.display.get_driver()
        if driver != "dummy":
            raise SystemExit(f"dummy 以外のドライバ（{driver}）では測らない")
        screen = pygame.display.set_mode(SPEC.size)
        window = pygame.Surface(SPEC.size, pygame.SRCALPHA, 32)
        scene = Scene(SPEC, random.Random(args.seed))
        runs: list[Run] = []
        for _ in range(args.runs):
            before = load_average()
            started = time.strftime("%H:%M:%S")
            stats = measure_run(
                scene, (screen, window), args.rounds, args.frames, args.warmup
            )
            runs.append(Run(started, before, load_average(), stats))
        choice = choose([run.stats for run in runs])
        if args.json:
            report = {
                **environment(),
                "tile": SPEC.tile,
                "particle_kind": SPEC.particle_kind,
                "frames": args.frames,
                "warmup": args.warmup,
                "rounds": args.rounds,
                "choice": None if choice is None else asdict(choice),
                "runs": [asdict(run) for run in runs],
            }
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print_table(runs, choice, environment())
    finally:
        pygame.display.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
