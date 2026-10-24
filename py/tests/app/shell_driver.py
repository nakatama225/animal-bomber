"""画面の流れ（`app/shell.py` の `Shell`）を、台本のイベントで回すための手伝い。

窓は開かない（`Shell` は窓の大きさの `pygame.Surface` に描くだけ）。音・曲・パッド・
中継は偽物に差し替え、何を鳴らしたか・何を送ったかを控える。時刻（ms）はフレームごとに
決めた量だけ進める。
"""

import itertools
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field

import pygame

from animal_bomber.app.lan import RelayConnection
from animal_bomber.app.shell import Shell, ShellTools
from animal_bomber.domain.rules.animals import Animal
from animal_bomber.presentation.audio.score import TEMPO
from animal_bomber.presentation.audio.sounds import SoundName
from animal_bomber.presentation.menu.items import MenuItem
from animal_bomber.presentation.render.baked.art import BakedArt
from animal_bomber.presentation.render.layout import WindowLayout, fit_window
from animal_bomber.presentation.render.ui.typeset import TextPainter
from animal_bomber.shell.gamepad import PadButton, PadSnapshot
from animal_bomber.shell.keyboard import KeyboardWatcher
from animal_bomber.shell.relay_link import RelayUnavailable, parse_relay_address

FRAME_MS = 1000 / 60
"""1フレームに進める時刻（ms）。"""

WINDOW: WindowLayout = fit_window(900, 700, panel_height=900, max_height=700)
"""テストの窓（マス 26。盤面 630×474 に枠 3px を付け、窓 890×700）。

横の板は窓より高くなりうる。
"""

PAINTER = TextPainter()
"""画面の文を描くもの（取っておいた文の絵を、テストのあいだ使い回す）。"""

SEED = 1000
"""試合の種の始め（試合を作るたびに 1 ずつ増える）。"""

HOST_ADDRESS = "localhost:8777"


class FakePads:
    """パッドの読み取りの代わり。繋がっているパッドと、対応していない機器を差し替える。"""

    def __init__(self) -> None:
        self.pads: list[PadSnapshot] = []
        self.unsupported: tuple[str, ...] = ()
        self.reads = 0

    def __call__(self) -> list[PadSnapshot]:
        self.reads += 1
        return list(self.pads)

    def hold(self, pad_id: int, *buttons: PadButton) -> None:
        """パッド `pad_id` を、`buttons` を押した状態にする（無ければ繋ぐ）。"""
        snapshot = PadSnapshot(pad_id, frozenset(buttons))
        others = [pad for pad in self.pads if pad.pad_id != pad_id]
        index = next(
            (i for i, pad in enumerate(self.pads) if pad.pad_id == pad_id), len(others)
        )
        others.insert(index, snapshot)
        self.pads = others


class FakeSounds:
    """効果音の代わり。鳴らした音と音量を控える。"""

    def __init__(self) -> None:
        self.played: list[SoundName] = []
        self.volume = 1.0

    def play(self, name: SoundName, intensity: int = 1) -> None:
        self.played.append(name)

    def set_volume(self, level: float) -> None:
        self.volume = level


class FakeTune:
    """曲の代わり。鳴らし始め・止めた回数と、音量・速さを控える。"""

    def __init__(self) -> None:
        self.log: list[str] = []
        self.volume = 1.0
        self.tempo = TEMPO

    def start(self) -> None:
        self.log.append("start")

    def stop(self) -> None:
        self.log.append("stop")

    def set_volume(self, level: float) -> None:
        self.volume = level

    def set_tempo(self, tempo: int) -> None:
        self.tempo = tempo

    @property
    def playing(self) -> bool:
        """最後にしたのが鳴らし始めか。"""
        return bool(self.log) and self.log[-1] == "start"


def refuse(address: str) -> RelayConnection:
    """中継につなげない（`RelayLink.open` の代わり）。"""
    raise RelayUnavailable("Connection refused")


def key_event(
    scancode: int, kind: int = pygame.KEYDOWN, text: str = ""
) -> pygame.event.Event:
    return pygame.event.Event(kind, scancode=scancode, key=0, unicode=text, mod=0)


@dataclass
class Driver:
    """`Shell` を1台ぶん回す。"""

    relay: str | None = None
    connect: Callable[[str], RelayConnection] = refuse
    seeds: Iterator[int] = field(default_factory=lambda: itertools.count(SEED))
    window: WindowLayout = WINDOW
    keyboard: KeyboardWatcher = field(default_factory=KeyboardWatcher)
    pads: FakePads = field(default_factory=FakePads)
    sounds: FakeSounds = field(default_factory=FakeSounds)
    music: FakeTune = field(default_factory=FakeTune)
    prepared: list[tuple[Animal, ...]] = field(default_factory=list)
    presented: int = 0
    now: float = 0.0
    on_prepare: Callable[[pygame.Surface], None] | None = None
    """絵を描いておくときに、そのときの描く面を渡す先（じゅんびちゅうを見るため）。"""

    def __post_init__(self) -> None:
        pygame.font.init()

        def prepare(art: BakedArt, animals: Sequence[Animal]) -> None:
            self.prepared.append(tuple(animals))
            if self.on_prepare is not None:
                self.on_prepare(self.shell.canvas)

        def present(canvas: pygame.Surface) -> None:
            self.presented += 1

        tools = ShellTools(
            window=self.window,
            keyboard=self.keyboard,
            pads=self.pads,
            painter=PAINTER,
            sounds=self.sounds,
            music=self.music,
            new_seed=self.seeds.__next__,
            connect=self.connect,
            host_address=HOST_ADDRESS,
            address_of=parse_relay_address,
            present=present,
            prepare=prepare,
        )
        self.shell = Shell(tools, relay=self.relay, started_ms=self.now)

    def frame(
        self, *events: pygame.event.Event, ticks: int = 1, ms: float = FRAME_MS
    ) -> bool:
        """時刻を `ms` 進めて、1フレーム回す。"""
        self.now += ms
        return self.shell.frame(ticks, list(events), self.now)

    def frames(self, count: int, ticks: int = 1) -> None:
        for _ in range(count):
            assert self.frame(ticks=ticks)

    def skip_splash(self) -> None:
        """何もしないまま起動の幕が消えるのを待つ（3.2 秒で消え始め、0.5 秒で外す）。"""
        self.frame(ticks=0, ms=3800)
        assert self.shell.flow.splash_view(self.now) is None

    def down(self, scancode: int, text: str = "") -> None:
        """キーを押す（離さない）フレーム。"""
        self.frame(key_event(scancode, text=text))

    def up(self, scancode: int) -> None:
        self.frame(key_event(scancode, pygame.KEYUP))

    def tap(self, scancode: int, text: str = "") -> None:
        """押して、次のフレームで離す。"""
        self.down(scancode, text)
        self.up(scancode)

    def item(self, label: str) -> MenuItem:
        """いま押せる項目のうち、文が `label` のもの。"""
        for hit in self.shell.hits:
            if hit.item.label == label:
                return hit.item
        labels = [hit.item.label for hit in self.shell.hits]
        raise AssertionError(f"「{label}」が無い: {labels}")

    def click(self, label: str, ticks: int = 0) -> None:
        """いま押せる項目のうち、文が `label` のものをマウスで押す。

        `ticks` は押すフレームに輪が返す tick の数（`click_at`）。
        """
        for hit in self.shell.hits:
            if hit.item.label == label:
                self.click_at(hit.rect.center, ticks)
                return
        labels = [hit.item.label for hit in self.shell.hits]
        raise AssertionError(f"「{label}」が無い: {labels}")

    def click_at(self, pos: tuple[int, int], ticks: int = 0) -> None:
        """`pos` をマウスで押して離すフレームを1つ回す。

        既定の `ticks` は 0（押したフレームに試合を進めない）。実機の輪は、最初の
        フレームのほかは 1 以上を返すので、押したフレームの進め方を見るときは 1 を渡す。
        """
        down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1)
        up = pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1)
        self.frame(down, up, ticks=ticks)

    def move_mouse(self, pos: tuple[int, int]) -> None:
        self.frame(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0)), ticks=0)

    def wheel(self, amount: float) -> None:
        """ホイールを回す（正が上）。"""
        event = pygame.event.Event(
            pygame.MOUSEWHEEL, x=0, y=round(amount), precise_x=0.0, precise_y=amount
        )
        self.frame(event, ticks=0)
