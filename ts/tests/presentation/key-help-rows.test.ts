import { describe, expect, it } from 'vitest';

import { tick } from '../../src/domain/core/Tick.js';
import type { PlayerId } from '../../src/domain/state/PlayerState.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { describeKeyHelp, keyHelpText, type KeyHelpRow, type KeyHelpSource } from '../../src/presentation/hud/keyHelp.js';
import type { Controller, Roster } from '../../src/presentation/hud/roster.js';
import { makeWorld } from '../helpers.js';

/**
 * 横の板のキーの案内の中身（原型の `renderKeyHelp`。L5560-5616）。
 *
 * 期待する文は、Python 版の `tests/presentation/test_key_help.py` の期待値（原型の文と1字ずつ突き合わせたもの）を写した。
 * キーは [] で囲んで読む（`keyHelpText`）。
 */

const human = (label: string, local = false): Controller => ({ kind: 'human', label, local });
const CPU: Controller = { kind: 'cpu', level: 'normal' };
const SOLO: Roster = [human('1P'), CPU, CPU, CPU];
const DUO: Roster = [human('1P'), human('2P'), CPU, CPU];

const SOLO_ROWS = [
  'そうさ',
  'うごく [W][A][S][D] / [↑][←][↓][→]',
  'ばくだん [Space][Enter][Z][/]',
  'とぶ [E][Q][X][C][R][Shift]（長押しでとくぎ🍗）',
];

const LANE_NOTE = '生きてるヤツに当てると交代して復活（HP1・パワーアップは維持）。残り1分で退場';

function source(
  world: WorldState,
  roster: Roster,
  options: { pad?: boolean; padInMatch?: boolean; paused?: boolean; canPause?: boolean } = {},
): KeyHelpSource {
  return {
    world,
    roster,
    padConnected: options.pad ?? false,
    padInMatch: options.padInMatch ?? true,
    paused: options.paused ?? false,
    canPause: options.canPause ?? true,
  };
}

const texts = (rows: readonly KeyHelpRow[]): string[] => rows.map(keyHelpText);

function toLane(world: WorldState, id: PlayerId): void {
  const player = world.players[id];
  if (player === undefined) throw new Error(`プレイヤー ${id} がいない`);
  player.life = { kind: 'negibon', along: 0, readyAt: tick(0) };
}

describe('操作の段', () => {
  it('人間が1なら「そうさ」の形で、技の行の頭はその動物の技の呼び方', () => {
    const rows = describeKeyHelp(source(makeWorld(1, ['rabbit', 'fox', 'mole', 'frog']), SOLO));
    expect(texts(rows)).toEqual([...SOLO_ROWS, '[P] ポーズ']);
    expect(rows[0]?.spans[0]?.kind).toBe('bold');
    expect(rows.at(-1)).toMatchObject({ marginTop: 7, opacity: 0.8 });
  });

  it('人間が2なら「1P」「2P」の形で、それぞれのキーだけを出す', () => {
    const rows = describeKeyHelp(source(makeWorld(1, ['rabbit', 'frog', 'fox', 'mole']), DUO));
    expect(texts(rows)).toEqual([
      '1P 🐰',
      '[W][A][S][D] ／ ばくだん [Space][Z]',
      'とぶ [E][Q][X][C][R][左Shift]（長押しでとくぎ🍗）',
      '2P 🐸',
      '[↑][←][↓][→] ／ ばくだん [Enter][/]',
      'した [右Shift][.][,][M][N]（長押しでとくぎ🍗）',
      '[P] ポーズ',
    ]);
    expect(rows[3]?.marginTop).toBe(7);
  });

  it.each([
    ['rabbit', 'とぶ'],
    ['frog', 'した'],
    ['fox', 'ドン置き'],
    ['elephant', 'はなみず'],
    ['mole', 'とくぎ🍗'],
  ])('技の呼び方は動物ごと（%s は「%s」）', (animal, label) => {
    const rows = describeKeyHelp(source(makeWorld(1, [animal, 'fox']), [human('1P'), CPU]));
    expect(keyHelpText(rows[3]!).startsWith(`${label} [E]`)).toBe(true);
  });

  it('CPU のプレイヤーは数えない（CPU だけの試合は2人の形で、見出しの絵文字は空・技は「技」）', () => {
    const rows = describeKeyHelp(source(makeWorld(1, ['rabbit', 'frog']), [CPU, CPU]));
    expect(texts(rows).slice(0, 3)).toEqual([
      '1P ',
      '[W][A][S][D] ／ ばくだん [Space][Z]',
      '技 [E][Q][X][C][R][左Shift]（長押しでとくぎ🍗）',
    ]);
  });
});

describe('パッドとポーズの行', () => {
  const ONE: Roster = [human('1P'), CPU];

  it('パッドを認識していて、パッドを試合に繋ぐ遊び方なら、パッドの段を出し、ポーズの行に Start を足す', () => {
    const helpRows = describeKeyHelp(source(makeWorld(1, ['frog', 'fox']), ONE, { pad: true }));
    expect(texts(helpRows).slice(4)).toEqual([
      '🎮 [十字][スティック] うごく ／ ばくだん [A][R1]',
      'した [B][X][Y][L1]（長押しでとくぎ🍗）',
      '[P][Start] ポーズ',
    ]);
    // パッドの段の1行目だけ、上に間を空ける（原型 L5604 の margin-top:7px）。
    expect(helpRows[4]).toMatchObject({ marginTop: 7, opacity: 1 });
    expect(helpRows[5]).toMatchObject({ marginTop: 0, opacity: 1 });
  });

  it('パッドが無ければ、パッドの段も Start も出さない', () => {
    const rows = texts(describeKeyHelp(source(makeWorld(1, ['frog', 'fox']), ONE)));
    expect(rows.some((row) => row.includes('🎮') || row.includes('Start'))).toBe(false);
  });

  it('2人の遊び方では、パッドを認識していてもパッドの段を出さない（Start は出す）。ポーズ中も Select の行を出さない', () => {
    const world = makeWorld(1, ['rabbit', 'frog']);
    const rows = texts(describeKeyHelp(source(world, DUO, { pad: true, padInMatch: false })));
    expect(rows.some((row) => row.includes('🎮'))).toBe(false);
    expect(rows.at(-1)).toBe('[P][Start] ポーズ');
    expect(rows.some((row) => row.includes('Select'))).toBe(false);
    // Select の行は、パッドを試合に繋ぐ遊び方だけ（原型 L5612 の `CFG.mode` の条件）。
    const paused = texts(describeKeyHelp(source(world, DUO, { pad: true, padInMatch: false, paused: true })));
    expect(paused.some((row) => row.includes('Select'))).toBe(false);
    expect(paused).toEqual(rows);
  });

  it('Select の行は、ポーズ中だけ', () => {
    const world = makeWorld(1, ['rabbit', 'frog']);
    const playing = texts(describeKeyHelp(source(world, ONE, { pad: true })));
    const pausedRows = describeKeyHelp(source(world, ONE, { pad: true, paused: true }));
    const paused = texts(pausedRows);
    expect(playing.some((row) => row.includes('Select'))).toBe(false);
    expect(paused.at(-1)).toBe('[Select] 設定へもどる');
    expect(paused.slice(0, -1)).toEqual(playing);
    // 薄く出す（原型 L5613 の opacity:.8）。上の間は空けない。
    expect(pausedRows.at(-1)).toMatchObject({ marginTop: 0, opacity: 0.8 });
  });

  it('ポーズできない端末は、ポーズの行を出さず、パッドがあれば Select の行をいつも出す', () => {
    const world = makeWorld(1, ['rabbit', 'frog']);
    const roster: Roster = [human('1P', true), human('2P')];
    const rows = texts(describeKeyHelp(source(world, roster, { pad: true, canPause: false })));
    expect(rows.some((row) => row.includes('ポーズ'))).toBe(false);
    expect(rows.at(-1)).toBe('[Select] 設定へもどる');
    const noPad = texts(describeKeyHelp(source(world, roster, { canPause: false })));
    expect(noPad.some((row) => row.includes('Select') || row.includes('ポーズ'))).toBe(false);
  });
});

describe('葱ボンの段', () => {
  it('外周にいる人間には、いちばん上に移動と発射のキーと注記を出す', () => {
    const world = makeWorld(1, ['rabbit', 'fox']);
    toLane(world, 0);
    const rows = describeKeyHelp(source(world, [human('1P'), CPU]));
    expect(texts(rows).slice(0, 5)).toEqual([
      '🌿 うさぎ は葱ボン＝場外',
      '外周を移動 [W][A][S][D] / [↑][←][↓][→]',
      '葱を発射 [Space] か [Enter]',
      LANE_NOTE,
      '---',
    ]);
    expect(texts(rows).slice(5, 9)).toEqual(SOLO_ROWS);
    const note = rows[3]!;
    expect(note.spans.map((span) => span.kind)).toEqual(['text', 'bold', 'text']);
    expect(note.spans[1]?.text).toBe('交代して復活');
    expect(note).toMatchObject({ marginTop: 5, opacity: 0.85 });
    expect(rows[4]?.rule).toBe(true);
  });

  it.each([
    [0, '🌿 うさぎ（1P） は葱ボン＝場外', '外周を移動 [W][A][S][D]', '葱を発射 [Space] か [Z]'],
    [1, '🌿 かえる（2P） は葱ボン＝場外', '外周を移動 [↑][←][↓][→]', '葱を発射 [Enter] か [/]'],
  ] as const)('2人のときは、札を添えて、それぞれのキーだけ（%i 番）', (id, heading, move, fire) => {
    const world = makeWorld(1, ['rabbit', 'frog']);
    toLane(world, id);
    const rows = texts(describeKeyHelp(source(world, [human('1P'), human('2P')])));
    expect(rows.slice(0, 3)).toEqual([heading, move, fire]);
    expect(rows[5]).toBe('1P 🐰');
  });

  it('外周にいる CPU には出さない', () => {
    const world = makeWorld(1, ['rabbit', 'fox']);
    toLane(world, 1);
    const rows = texts(describeKeyHelp(source(world, [human('1P'), CPU])));
    expect(rows[0]).toBe('そうさ');
    expect(rows.some((row) => row.includes('葱ボン'))).toBe(false);
  });
});

describe('通信対戦', () => {
  it('この端末のプレイヤーだけを、1人の形で出す（原型は人間の数で2人の形にする）', () => {
    const world = makeWorld(1, ['rabbit', 'frog', 'fox', 'elephant']);
    const roster: Roster = [human('1P'), human('2P', true), CPU, human('4P')];
    toLane(world, 0);
    toLane(world, 1);
    const rows = texts(describeKeyHelp(source(world, roster, { pad: true, canPause: false })));
    expect(rows[0]).toBe('🌿 かえる は葱ボン＝場外');
    expect(rows.some((row) => row.includes('うさぎ'))).toBe(false);
    expect(rows).toContain('そうさ');
    expect(rows).toContain('した [E][Q][X][C][R][Shift]（長押しでとくぎ🍗）');
    expect(rows).toContain('した [B][X][Y][L1]（長押しでとくぎ🍗）');
    expect(rows.some((row) => row.startsWith('1P') || row.startsWith('2P'))).toBe(false);
  });
});
