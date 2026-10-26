import { describe, expect, it } from 'vitest';

import { keyName, menuHelp, PAD_MENU_HELP } from '../../src/platform/keyHelp.js';
import { describeManual } from '../../src/platform/ui/manual.js';
import { KEY_HINT_P1, KEY_HINT_P2, KEY_HINT_SOLO } from '../../src/presentation/menu/keyHints.js';

describe('キーの呼び方', () => {
  it('キーの呼び方を縮める', () => {
    expect(['KeyW', 'ArrowUp', 'Space', 'Slash', 'ShiftLeft', 'Digit1'].map(keyName)).toEqual([
      'W',
      '↑',
      'Space',
      '/',
      '左Shift',
      '1',
    ]);
  });
});

describe('遊び方の説明', () => {
  it('とくぎの長押しの長さと、通常技が無く押すとすぐとくぎが出る動物を、能力の表から出す', () => {
    const lines = describeManual().find((section) => section.title === '技ととくぎ')?.lines ?? [];
    const lineOf = (name: string): string => lines.find((line) => line.includes(name)) ?? '';
    expect(lineOf('うさぎ')).toContain('0.5 秒');
    expect(lineOf('うさぎ')).not.toContain('通常技は無く');
    expect(lineOf('ぞう')).toContain('1.5 秒');
    // ぞうは押した瞬間に鼻水を吹く（原型の通常技）。
    expect(lineOf('ぞう')).not.toContain('通常技は無く');
    expect(lineOf('もぐら')).toContain('通常技は無く、押すとすぐとくぎが出る');
  });

  it('そうさの説明は、キャラ選びと同じ原型の固定の文（割り当てた J と Option は書かない）', () => {
    const linesOf = (title: string): readonly string[] =>
      describeManual().find((section) => section.title === title)?.lines ?? [];
    expect(linesOf('そうさ（1人で遊ぶとき・通信対戦）')).toEqual([KEY_HINT_SOLO]);
    expect(linesOf('そうさ（1台で2人のとき）').slice(0, 2)).toEqual([`1P ${KEY_HINT_P1}`, `2P ${KEY_HINT_P2}`]);
    const keyLines = [...linesOf('そうさ（1人で遊ぶとき・通信対戦）'), ...linesOf('そうさ（1台で2人のとき）')].join('\n');
    expect(keyLines).not.toMatch(/\bJ\b|Option|Alt/);
  });
});

describe('メニューの動かし方の説明', () => {
  it('メニューの操作の表から作り、遊び方の説明にも出す', () => {
    const line = '↑ ← ↓ → で選び、Enter・Space で決める。Escape・Backspace で1つ前の画面へ（マウスでも押せる）';
    expect(menuHelp()).toBe(line);
    expect(describeManual().find((section) => section.title === 'メニュー')?.lines).toEqual([
      line,
      PAD_MENU_HELP,
      '通信対戦のロビーでは、戻るは効かない（ぬけるときは「← ぬける」を押す）',
    ]);
  });
});
