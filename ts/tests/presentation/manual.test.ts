import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';

import { CHANGELOG, LEGEND, MANUAL, VERSION, VERSION_LINE, type ManualSpan } from '../../src/presentation/menu/manual.js';

/**
 * マニュアルと更新履歴の文（`presentation/menu/manual.ts`）が、Python 版の文と1字も違わないか。
 *
 * 文の正は Python 版の `presentation/menu/manual.py`（原型の文を逐語で写し、書かない語だけを言い換えたもの）。
 * このテストは `../py` を読まない（テストの写しの上でも走らせるため）。代わりに、Python 版の文を JSON にして
 * SHA-256 を取った値を期待値に持つ。Python 版では次の形で出す：
 *
 * ```python
 * json.dumps([[[s.kind.value, s.text] for s in line] for line in MANUAL], ensure_ascii=False, separators=(",", ":"))
 * json.dumps([[e.version, e.kind.value, e.large, [[s.kind.value, s.text] for s in e.body]] for e in CHANGELOG], …)
 * json.dumps([[kind.value, label, after] for kind, label, after in LEGEND], …)
 * ```
 *
 * を UTF-8 にして `hashlib.sha256`。Python 版の文を変えたら、`manual.ts` を書き出し直し、この値も計算し直す。
 * どちらも `ts/tools/gen_manual.py` が行う（リポジトリのいちばん上で `uv --directory py run python ../ts/tools/gen_manual.py`。
 * 値は標準出力に書かれる）。
 */
const PYTHON_MANUAL_SHA256 = '0fe2d1b0af399f843ee28725e024ebb242d209afcc9e9ed59477e699fd2ce2e1';
const PYTHON_CHANGELOG_SHA256 = 'cf0d681521681323e8cc9b0dffcea4b15e4b6d9f36fe103876828bd99dd602e2';
const PYTHON_LEGEND_SHA256 = '097b6b3b7cd28f4460ebb88b8810f60b8aceb30c2b205840e1ae178772548b52';

const sha256 = (value: unknown): string => createHash('sha256').update(JSON.stringify(value), 'utf8').digest('hex');
const spans = (list: readonly ManualSpan[]): [string, string][] => list.map((span) => [span.kind, span.text]);
const plain = (list: readonly ManualSpan[]): string => list.map((span) => span.text).join('');

const manualText = MANUAL.map(plain).join('\n');
const logText = CHANGELOG.map((entry) => `${entry.version}${plain(entry.body)}`).join('\n');

/** 原型の文のうち、リポジトリの文の決まりで書かない語（字の番号で持つ。この語をファイルに書かないため）。 */
const ORIGINAL = {
  /** 原型 L387・L392・2.3.3 の語（Python 版の言い換えは「反応しない」） */
  noEffect: String.fromCodePoint(0x52b9, 0x304b, 0x306a, 0x3044),
  /** 原型の 2.3.10・2.3.8 の語（Python 版の言い換えは「効果」） */
  effectNoun: String.fromCodePoint(0x52b9, 0x304d),
  /** 原型 L403 の語（Python 版の言い換えは「側」） */
  self: String.fromCodePoint(0x672c, 0x4eba),
  /** 原型の 4.3.0・3.0.0 の「回線が切れた」のあとの語（Python 版の言い換えは「プレイヤー」） */
  droppedPerson: `切れた${String.fromCodePoint(0x4eba)}`,
};

/**
 * 凡例の PATCH の原型の語（L449。Python 版の言い換えは「修正した・調整した」）。更新履歴の本文の 2.3.0 には、
 * 同じ字の並びを含む別の語が原型のまま残るので、凡例だけで見る。
 */
const ORIGINAL_REPAIRED = String.fromCodePoint(0x76f4, 0x3057, 0x305f);

describe('マニュアルと更新履歴の文', () => {
  it('マニュアルの行は、Python 版の MANUAL と1字も違わない', () => {
    expect(MANUAL).toHaveLength(46);
    expect(sha256(MANUAL.map(spans))).toBe(PYTHON_MANUAL_SHA256);
  });

  it('更新履歴の 49 項目は、Python 版の CHANGELOG と1字も違わない', () => {
    expect(CHANGELOG).toHaveLength(49);
    expect(sha256(CHANGELOG.map((entry) => [entry.version, entry.kind, entry.large, spans(entry.body)]))).toBe(
      PYTHON_CHANGELOG_SHA256,
    );
  });

  it('凡例は、Python 版の LEGEND と1字も違わない（PATCH は「修正した・調整した」）', () => {
    expect(sha256(LEGEND.map((entry) => [entry.kind, entry.label, entry.after]))).toBe(PYTHON_LEGEND_SHA256);
    expect(LEGEND.map((entry) => entry.label)).toEqual(['MAJOR', 'MINOR', 'PATCH']);
    expect(LEGEND[2]?.after).toBe('＝修正した・調整した');
    expect(LEGEND.map((entry) => entry.after).join('')).not.toContain(ORIGINAL_REPAIRED);
  });

  it('版の並びは原型の 4.3.0 から 1.0.0 まで（新しい版から）', () => {
    expect(CHANGELOG.map((entry) => entry.version)).toEqual([
      '4.3.0', '4.2.1', '4.2.0', '4.1.0', '4.0.0', '3.0.2', '3.0.1', '3.0.0', '2.3.10', '2.3.9', '2.3.8', '2.3.7',
      '2.3.6', '2.3.4', '2.3.3', '2.3.2', '2.3.1', '2.3.0', '2.2.0', '2.1.0', '2.0.4', '2.0.3', '2.0.2', '2.0.1',
      '2.0.0', '1.7.3', '1.7.2', '1.7.1', '1.7.0', '1.6.2', '1.6.1', '1.6.0', '1.5.1', '1.5.0', '1.4.2', '1.4.1',
      '1.4.0', '1.3.3', '1.3.2', '1.3.1', '1.3.0', '1.2.1', '1.2.0', '1.1.2', '1.1.1', '1.1.0', '1.0.2', '1.0.1',
      '1.0.0',
    ]);
  });

  it('PATCH なのに大きい字で書くのは 4.2.1 だけ。ほかの PATCH は小さい字、MAJOR と MINOR は大きい字', () => {
    expect(CHANGELOG.filter((entry) => entry.kind === 'patch' && entry.large).map((entry) => entry.version)).toEqual(['4.2.1']);
    expect(CHANGELOG.filter((entry) => entry.kind !== 'patch' && !entry.large)).toEqual([]);
    expect(CHANGELOG.filter((entry) => entry.kind === 'major').map((entry) => entry.version)).toEqual(['4.0.0', '3.0.0', '2.0.0', '1.0.0']);
  });

  it('プログラムの字の区切りは 1.0.2 の `undefined.timer` の1か所だけ', () => {
    const code = CHANGELOG.flatMap((entry) => entry.body.filter((span) => span.kind === 'code').map((span) => [entry.version, span.text]));
    expect(code).toEqual([['1.0.2', 'undefined.timer']]);
    expect(MANUAL.flat().some((span) => span.kind === 'code')).toBe(false);
  });

  it('マニュアルにきつねの古い行（爆弾のボタンで一列に置く。原型 L401）を写さず、うさぎの跳躍の行は2つとも写す', () => {
    expect(manualText).not.toContain('常に正面へ');
    expect(manualText).toContain('・🦊きつねは技ボタンで一列ドン設置');
    const jumps = MANUAL.filter((line) => plain(line).startsWith('・🐰うさぎの跳躍は'));
    expect(jumps.map((line) => line.find((span) => span.kind === 'bold')?.text)).toEqual(['2秒に1回', '2秒インターバル']);
  });

  it('原型の文のうち、書かない語に当たる所は Python 版の言い換えになっている', () => {
    expect(manualText).toContain('2人プレイではコントローラーは反応しない');
    expect(MANUAL.flat()).toContainEqual({ kind: 'bold', text: '反応しないときは Bluetooth を疑う' });
    expect(manualText).toContain('撒いた側は踏んでも平気');
    expect(logText).toContain('回線が切れたプレイヤーが1人いるだけで');
    expect(logText).toContain('そのプレイヤーの枠だけ CPU が引き継いで');
    expect(logText).toContain('回線が切れたプレイヤーはCPUが引き継ぐ');
    expect(logText).toContain('👟の効果を10%→通常と同じ倍率に戻した');
    expect(logText).toContain('👟 の効果を通常の10%に');
    expect(logText).toContain('option だと たまに反応しないので');
    expect(logText).toContain('強さ設定が反映されない');
    for (const word of Object.values(ORIGINAL)) {
      expect(manualText).not.toContain(word);
      expect(logText).not.toContain(word);
    }
  });

  it('キーは1つずつの区切りで持つ（並んだキーの間に空白を入れない。原型の `<kbd>` の並び）', () => {
    const first = MANUAL[0] ?? [];
    expect(first.slice(0, 6)).toEqual([
      { kind: 'bold', text: '1人プレイ' },
      { kind: 'text', text: '　' },
      { kind: 'key', text: 'W' },
      { kind: 'key', text: 'A' },
      { kind: 'key', text: 'S' },
      { kind: 'key', text: 'D' },
    ]);
  });

  it('版の行は原型の版（v4.3.0）', () => {
    expect(VERSION).toBe('v4.3.0');
    expect(VERSION_LINE).toBe('VERSION v4.3.0');
  });
});
