"""Python 版のマニュアルと更新履歴の文を、TypeScript 版へ機械的に書き出す。

Python 版の manual.py の MANUAL・CHANGELOG・LEGEND を、src/presentation/menu/manual.ts にする。

リポジトリのいちばん上から、Python 版の環境で実行する（Python 版の文を import するため）：

    uv --directory py run python ../ts/tools/gen_manual.py

manual.ts を書き換え、テスト（tests/presentation/manual.test.ts）が比べる SHA-256 の値（JSON にした文の）を
計算して標準出力に書く。Python 版の文を変えたら、これを実行し、書かれた値をテストの期待値に写す。
"""

import hashlib
import json
from pathlib import Path

from animal_bomber.presentation.menu.manual import (
    CHANGELOG,
    LEGEND,
    MANUAL,
    VERSION,
)

OUT = Path(__file__).resolve().parents[1] / "src" / "presentation" / "menu" / "manual.ts"

CHUNK = 48
# 長い文を 48 字で分けるとき、この字の前では切らない（絵文字の異体字の選択子・ゼロ幅の接合子・囲みの記号）。
JOINERS = {"️", "‍", "⃣"}


def quote(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("'", "\\'")
    for ch in escaped:
        if ord(ch) < 0x20:
            raise ValueError(f"制御文字がある: {text!r}")
    return f"'{escaped}'"


def literal(text: str, indent: str) -> str:
    """長い文は 48 字ずつに分けて + でつなぐ（値は同じ）。"""
    if len(text) <= CHUNK + 12:
        return quote(text)
    parts: list[str] = []
    rest = text
    while len(rest) > CHUNK + 12:
        cut = CHUNK
        while cut < len(rest) and rest[cut] in JOINERS:
            cut += 1
        parts.append(rest[:cut])
        rest = rest[cut:]
    parts.append(rest)
    return (" +\n" + indent + "  ").join(quote(part) for part in parts)


def spans_code(spans, indent: str) -> list[str]:
    """区切りの並びを、1区切り（キーはまとめて1つ）ずつの行にする。"""
    lines: list[str] = []
    keys: list[str] = []

    def flush() -> None:
        if keys:
            lines.append(f"{indent}...k({', '.join(quote(name) for name in keys)}),")
            keys.clear()

    for span in spans:
        kind = span.kind.value
        if kind == "key":
            keys.append(span.text)
            continue
        flush()
        fn = {"text": "t", "bold": "b", "code": "c"}[kind]
        lines.append(f"{indent}{fn}({literal(span.text, indent)}),")
    flush()
    return lines


def main() -> None:
    out: list[str] = []
    out.append(HEADER.strip("\n"))
    out.append("")
    out.append("/** 原型の版（`const VERSION`。L5673）。更新履歴もこの版までの 49 項目。 */")
    out.append(f"export const VERSION = {quote(VERSION)};")
    out.append("")
    out.append("/** タイトルと起動の幕に出す版の行（原型の `VERSION ${VERSION}`。L5750）。 */")
    out.append("export const VERSION_LINE = `VERSION ${VERSION}`;")
    out.append("")
    out.append(TYPES.strip("\n"))
    out.append("")
    out.append("/**")
    out.append(" * 更新履歴の凡例（原型 L446-450）。札のあとの文の末尾の全角と半角の空白は、原型の HTML の空白のまま。")
    out.append(" */")
    out.append("export const LEGEND: readonly LegendEntry[] = [")
    for kind, label, after in LEGEND:
        out.append(f"  {{ kind: {quote(kind.value)}, label: {quote(label)}, after: {quote(after)} }},")
    out.append("];")
    out.append("")
    out.append("/** マニュアルの行（原型 L365-441。L401 は写さない）。空の行は、空けた行（原型の `<br><br>`）。 */")
    out.append("export const MANUAL: readonly ManualLine[] = [")
    for line in MANUAL:
        if not line:
            out.append("  [],")
            continue
        out.append("  [")
        out.extend(spans_code(line, "    "))
        out.append("  ],")
    out.append("];")
    out.append("")
    out.append("/** 更新履歴の 49 項目（原型 L452-507。新しい版から）。 */")
    out.append("export const CHANGELOG: readonly ChangelogEntry[] = [")
    for entry in CHANGELOG:
        out.append("  {")
        out.append(f"    version: {quote(entry.version)},")
        out.append(f"    kind: {quote(entry.kind.value)},")
        out.append(f"    large: {'true' if entry.large else 'false'},")
        out.append("    body: [")
        out.extend(spans_code(entry.body, "      "))
        out.append("    ],")
        out.append("  },")
    out.append("];")
    out.append("")
    OUT.write_text("\n".join(out), encoding="utf-8")

    def dump(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    manual_json = dump([[[s.kind.value, s.text] for s in line] for line in MANUAL])
    log_json = dump(
        [[e.version, e.kind.value, e.large, [[s.kind.value, s.text] for s in e.body]] for e in CHANGELOG]
    )
    legend_json = dump([[kind.value, label, after] for kind, label, after in LEGEND])
    hashes = {
        "manual": hashlib.sha256(manual_json.encode("utf-8")).hexdigest(),
        "changelog": hashlib.sha256(log_json.encode("utf-8")).hexdigest(),
        "legend": hashlib.sha256(legend_json.encode("utf-8")).hexdigest(),
        "manual_lines": len(MANUAL),
        "changelog_entries": len(CHANGELOG),
    }
    print(json.dumps(hashes, ensure_ascii=False, indent=2))


HEADER = """
/**
 * 設定の画面に出す、マニュアルと更新履歴の文（原型の「② マニュアル」「③ 更新履歴」。L365-441・L444-509）。
 *
 * ⛔ このファイルを手で修正しないこと。Python 版の `py/src/animal_bomber/presentation/menu/manual.py` の
 * `MANUAL`・`CHANGELOG`・`LEGEND` を、同じ行と区切り（文・太字・キー・コード）のまま機械的に書き出した。
 * Python 版は原型の文を逐語で写し、HTML の空白の決まりのとおり、原文の改行と字下げを空白1つにまとめてある
 * （全角の空白は残る）。Python 版の文を変えたら、`ts/tools/gen_manual.py` で書き出し直す（実行の仕方は
 * その冒頭）。写し違いは `tests/presentation/manual.test.ts` が、Python 版の文から計算した SHA-256 の値と比べて見つける。
 *
 * 画面に出す文の正は Python 版にそろえる。Python 版は、リポジトリの文の決まりで書かない語に当たる所だけを
 * 熟語に言い換えてある（マニュアルの「反応しない」2か所・うんこを撒いた「側」、凡例の「修正した・調整した」、
 * 更新履歴の回線が切れた「プレイヤー」・👟の「効果」・「反応しない」・「反映されない」）。
 *
 * 写さなかった行：マニュアルのきつねの行のうち、爆弾のボタンで一列に置くと書いた古い行（原型 L401）。同じ
 * マニュアルの L417-418（技のボタンで1マス前から置く）が動きと合う。うさぎの跳躍の行は2つ（L406・L421）とも写した。
 *
 * マニュアルには、この版に当てはまらない説明も原型のまま残る（ブラウザがコントローラーを見つける仕組み・
 * USB で繋がないこと）。版は原型の版で、更新履歴もこの版の変更の履歴ではない。
 */
"""

TYPES = """
/** 行の中の1区切り。 */
export interface ManualSpan {
  /**
   * `text`：ふつうの文。`bold`：太字（原型の `<b>`）。`key`：キー1つ（原型の `<kbd>`）。
   * `code`：プログラムの字（原型の `<code>`。更新履歴の 1.0.2 の1か所だけ）。
   */
  readonly kind: 'text' | 'bold' | 'key' | 'code';
  readonly text: string;
}

/** マニュアルの1行（原型の `<br>` から `<br>` まで）。 */
export type ManualLine = readonly ManualSpan[];

/** 更新履歴の版の種類（原型の凡例）。版の字の色を決める（`major` は赤、`minor` は黄、`patch` は淡い色）。 */
export type VersionKind = 'major' | 'minor' | 'patch';

/** 更新履歴の1項目。 */
export interface ChangelogEntry {
  /** 版（「4.3.0」）。 */
  readonly version: string;
  readonly kind: VersionKind;
  /**
   * 大きい字で出すか（原型の `.lg`。小さい字で字下げするのは `.lp`）。
   *
   * ⚠️ 原型は 4.2.1 だけ、PATCH なのに大きい字で書いている。そのまま写した。
   */
  readonly large: boolean;
  /** 版の字のあとの本文。頭の空白（版の字との間）も原型のまま持つ。 */
  readonly body: readonly ManualSpan[];
}

/** 更新履歴の凡例の1つ（版の札と、札のあとの文）。 */
export interface LegendEntry {
  readonly kind: VersionKind;
  readonly label: string;
  readonly after: string;
}

const t = (text: string): ManualSpan => ({ kind: 'text', text });
const b = (text: string): ManualSpan => ({ kind: 'bold', text });
const c = (text: string): ManualSpan => ({ kind: 'code', text });
const k = (...names: readonly string[]): ManualSpan[] => names.map((name) => ({ kind: 'key', text: name }));
"""

if __name__ == "__main__":
    main()
