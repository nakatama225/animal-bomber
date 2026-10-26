"""音の表が、原型と同じ部品と値の動きを作ることの検査。

固定値（`legacy_sound_values.json`）は、原型（`legacy/animal-bomber.html`）を node で
読み込み、Web Audio を記録するだけの偽物に差し替えて、効果音 36 種（爆発は連鎖数 2 と 5
も）と、曲の 32 刻みを鳴らして書き出したもの。リポジトリのいちばん上で次を走らせると
作り直せる（乱数は書き出さないので、何度作っても同じものになる）。

    node py/tools/legacy_oracle/legacy_sound.js \
        py/tests/presentation/legacy_sound_values.json

記録は、鳴らした音1つごとに、出どころ（発音器かノイズ）から出口（効果音か曲の系統）
までの部品の並びと、部品ごとに入れた予定（`setValueAtTime`・
`exponentialRampToValueAtTime`・値の代入・始める・止める）を、入れた順に持つ。この版の
`voices.py` の `Voice` を同じ形に直して、種類・値・時刻まで比べる。

数値は相対・絶対とも 1e-9 まで許す。原型の `Math.pow(2, s/12)` と Python の
`2 ** (s / 12)` は、最後の桁が違うことがある。
"""

import json
import math
from pathlib import Path
from typing import Any

import pytest

from animal_bomber.presentation.audio.parts import Noise, Tone, Wave
from animal_bomber.presentation.audio.score import (
    ARP,
    BASS,
    STEP_SECONDS,
    TEMPO,
    step_voices,
)
from animal_bomber.presentation.audio.sounds import SoundName
from animal_bomber.presentation.audio.voices import (
    BUS_LEVEL,
    AssignValue,
    ExponentialRamp,
    NoiseLoop,
    Oscillator,
    ParamEvent,
    SetValue,
    Voice,
    noise_voice,
    tone_voice,
    voices_of,
)

FIXTURE: dict[str, Any] = json.loads(
    (Path(__file__).parent / "legacy_sound_values.json").read_text(encoding="utf-8")
)

LEGACY_NAMES: dict[SoundName, str] = {
    SoundName.PLACE: "place",
    SoundName.EXPLODE: "explode",
    SoundName.BREAK_BLOCK: "breakBlock",
    SoundName.ITEM: "item",
    SoundName.HURT: "hurt",
    SoundName.DIE: "die",
    SoundName.JUMP: "jump",
    SoundName.SPECIAL: "special",
    SoundName.TICK: "tick",
    SoundName.WIN: "win",
    SoundName.CHAMPION: "champion",
    SoundName.DRAW: "draw",
    SoundName.UI: "ui",
    SoundName.SLIP: "slip",
    SoundName.CRY: "cry",
    SoundName.CHICKEN: "chicken",
    SoundName.POOP: "poop",
    SoundName.BLOW_POOP: "blowPoop",
    SoundName.NEGI: "negi",
    SoundName.NEGI_HIT: "negiHit",
    SoundName.NEGI_OUT: "negiOut",
    SoundName.NEGI_BLOCK: "negiBlock",
    SoundName.SPIT: "spit",
    SoundName.CHARGE: "charge",
    SoundName.SLIME: "slime",
    SoundName.SLIME_HOP: "slimeHop",
    SoundName.SNOT: "snot",
    SoundName.FOXFIRE: "foxfire",
    SoundName.FOXFIRE_HIT: "foxfireHit",
    SoundName.TONGUE: "tongue",
    SoundName.TONGUE_CATCH: "tongueCatch",
    SoundName.PIT_DIG: "pitDig",
    SoundName.PIT_DONE: "pitDone",
    SoundName.PIT_FALL: "pitFall",
    SoundName.FOX_LEAP: "foxLeap",
    SoundName.SUDDEN: "sudden",
}
"""この版の音の名前と、原型の `SE` の名前の対応。"""

BY_LEGACY_NAME = {legacy: name for name, legacy in LEGACY_NAMES.items()}

Node = tuple[str, Any]
"""部品1つ（種類と、その部品の記録）。"""


def _rows(events: tuple[ParamEvent, ...]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for event in events:
        match event:
            case SetValue(value=value, time=time):
                rows.append(["setValueAtTime", value, time])
            case ExponentialRamp(value=value, time=time):
                rows.append(["exponentialRampToValueAtTime", value, time])
            case AssignValue(value=value):
                rows.append(["value", value])
    return rows


def nodes_of_voice(voice: Voice) -> list[Node]:
    """この版の `Voice` を、記録と同じ形（部品の並び）に直す。"""
    nodes: list[Node] = []
    match voice.source:
        case Oscillator(wave=wave, frequency=frequency):
            nodes.append(
                (
                    "oscillator",
                    {
                        "type": wave.value,
                        "frequency": _rows(frequency),
                        "start": voice.start,
                        "stop": voice.stop,
                    },
                )
            )
        case NoiseLoop():
            nodes.append(
                (
                    "bufferSource",
                    {"loop": True, "start": voice.start, "stop": voice.stop},
                )
            )
    if voice.filter is not None:
        props: dict[str, Any] = {
            "type": voice.filter.kind.value,
            "frequency": _rows(voice.filter.frequency),
        }
        if voice.filter.q:
            props["Q"] = _rows(voice.filter.q)
        nodes.append(("biquad", props))
    nodes.append(("gain", {"gain": _rows(voice.gain)}))
    nodes.append(("bus", voice.bus.value))
    return nodes


def nodes_of_record(chain: list[dict[str, Any]]) -> list[Node]:
    """原型の記録1つ（部品の並び）を、部品ごとに値の名前で分けた形にする。"""
    nodes: list[Node] = []
    for node in chain:
        if "bus" in node:
            nodes.append(("bus", node["bus"]))
            continue
        props: dict[str, Any] = {}
        for row in node["log"]:
            match row:
                case ["type" | "loop" | "start" | "stop" as key, value]:
                    props[key] = value
                case [param, method, *args]:
                    props.setdefault(param, []).append([method, *args])
                case _:
                    raise ValueError(f"読めない記録: {row!r}")
        nodes.append((node["kind"], props))
    return nodes


def assert_close(actual: Any, expected: Any, where: str = "") -> None:
    """入れ子の list・dict・tuple を比べる。数は相対・絶対とも 1e-9 まで許す。"""
    if isinstance(expected, bool) or isinstance(actual, bool):
        assert actual is expected, f"{where}: {actual!r} != {expected!r}"
    elif isinstance(expected, int | float) and isinstance(actual, int | float):
        assert math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9), (
            f"{where}: {actual!r} != {expected!r}"
        )
    elif isinstance(expected, dict):
        assert isinstance(actual, dict), f"{where}: {actual!r}"
        assert sorted(actual) == sorted(expected), f"{where}: {sorted(actual)}"
        for key in expected:
            assert_close(actual[key], expected[key], f"{where}.{key}")
    elif isinstance(expected, list | tuple):
        assert isinstance(actual, list | tuple), f"{where}: {actual!r}"
        assert len(actual) == len(expected), (
            f"{where}: 長さ {len(actual)} != {len(expected)}"
        )
        for index, (got, want) in enumerate(zip(actual, expected, strict=True)):
            assert_close(got, want, f"{where}[{index}]")
    else:
        assert actual == expected, f"{where}: {actual!r} != {expected!r}"


def _sound_case(key: str) -> tuple[SoundName, int]:
    """記録の鍵（`explode(2)` など）を、音の名前と連鎖数にする。"""
    if key.endswith(")"):
        legacy, count = key[:-1].split("(")
        return BY_LEGACY_NAME[legacy], int(count)
    return BY_LEGACY_NAME[key], 1


def test_音の名前は_原型の効果音36種と1対1() -> None:
    """原型に無い音を足したり、原型の音を落としたりしていない。"""
    assert set(LEGACY_NAMES) == set(SoundName)
    assert sorted(LEGACY_NAMES.values()) == sorted(FIXTURE["seNames"])
    assert len(FIXTURE["seNames"]) == 36
    # 値は原型の名前そのもの（`sounds.py` の説明）。
    assert {name: name.value for name in SoundName} == LEGACY_NAMES


def test_記録には_効果音36種と連鎖した爆発の2つがある() -> None:
    """表との比べ漏れが無いこと。

    下の比べるテストは、記録にある音だけを順に処理する。
    """
    assert sorted(FIXTURE["sounds"]) == sorted(
        [*FIXTURE["seNames"], "explode(2)", "explode(5)"]
    )


@pytest.mark.parametrize("key", sorted(FIXTURE["sounds"]))
def test_効果音は_原型と同じ部品と値の動きを作る(key: str) -> None:
    name, intensity = _sound_case(key)
    actual = [nodes_of_voice(voice) for voice in voices_of(name, intensity)]
    expected = [nodes_of_record(chain) for chain in FIXTURE["sounds"][key]]
    assert_close(actual, expected, key)


@pytest.mark.parametrize("entry", FIXTURE["bgm"], ids=lambda entry: str(entry["step"]))
def test_曲の刻みは_原型と同じ部品と値の動きを作る(entry: dict[str, Any]) -> None:
    """原型の刻みは 0〜31 を回る。16〜31 も、この版の 16 刻みの表で同じ音になる。"""
    step = entry["step"]
    assert math.isclose(entry["t"], step * STEP_SECONDS, rel_tol=1e-12)
    actual = [nodes_of_voice(voice) for voice in step_voices(step, entry["t"])]
    expected = [nodes_of_record(chain) for chain in entry["voices"]]
    assert_close(actual, expected, f"step {step}")


def test_系統の音量と曲の数値は_原型と同じ() -> None:
    assert {bus.value: level for bus, level in BUS_LEVEL.items()} == FIXTURE["buses"]
    assert FIXTURE["tempo"] == TEMPO
    assert list(BASS) == FIXTURE["bassPat"]
    assert list(ARP) == FIXTURE["arpPat"]
    # ノイズは 1 秒（`synth.py` の `white_noise` は、標本化の周波数の数だけ作る）。
    assert FIXTURE["noiseSeconds"] == 1


class Test下げる先の下限:
    """原型の `tone()` の `Math.max(20, f1)` と、`noiseBurst()` の `Math.max(40, f1)`。

    いまの表には、下限より下まで下げる音が無い（波形の音は爆発の 32 Hz がいちばん低く、
    ノイズは倒れたときの 60 Hz）。表との突き合わせでは下限が作用しないので、部品を直に
    作って確認する。
    """

    def test_波形の音は_20Hzより下へは下げない(self) -> None:
        voice = tone_voice(Tone(f0=100, f1=5, wave=Wave.SINE, dur=0.3))
        assert voice.source == Oscillator(
            Wave.SINE, (SetValue(100, 0), ExponentialRamp(20, 0.3))
        )

    def test_ノイズの削る境目は_40Hzより下へは下げない(self) -> None:
        voice = noise_voice(Noise(dur=0.2, f0=500, f1=10))
        assert voice.filter is not None
        assert voice.filter.frequency == (SetValue(500, 0), ExponentialRamp(40, 0.2))


class Test比べ方:
    """比べ方そのものが、違いを見逃さないことの確認。"""

    def test_値が1e_9を超えて違えば見つける(self) -> None:
        with pytest.raises(AssertionError):
            assert_close(
                [["setValueAtTime", 0.16, 0.0]], [["setValueAtTime", 0.1601, 0]]
            )

    def test_予定が1つ多ければ見つける(self) -> None:
        with pytest.raises(AssertionError):
            assert_close({"frequency": [[1], [2]]}, {"frequency": [[1]]})

    def test_値の名前が違えば見つける(self) -> None:
        with pytest.raises(AssertionError):
            assert_close({"Q": []}, {"frequency": []})
