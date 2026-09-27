import { describe, expect, it } from 'vitest';

import { keyHelpFor, keyName, menuHelp } from '../../src/platform/keyHelp.js';
import { PLAYER1_KEYS, PLAYER2_KEYS, SOLO_KEYS } from '../../src/platform/Keyboard.js';
import { describeManual } from '../../src/platform/ui/manual.js';

describe('キー配置の説明', () => {
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

  it('1人のときは、WASD と矢印を組ごとに並べる', () => {
    expect(keyHelpFor('1P', SOLO_KEYS).lines).toEqual([
      'うごく W A S D ／ ↑ ← ↓ →',
      'ばくだん Space Enter Z /',
      '技 E Q 左Shift 右Shift（長押しでとくぎ）',
    ]);
  });

  it('2人のときは、それぞれのキーだけを出す', () => {
    expect(keyHelpFor('1P', PLAYER1_KEYS).lines[0]).toBe('うごく W A S D');
    expect(keyHelpFor('2P', PLAYER2_KEYS).lines).toEqual([
      'うごく ↑ ← ↓ →',
      'ばくだん Enter /',
      '技 . , 右Shift（長押しでとくぎ）',
    ]);
  });

  it('説明は配置の表から作る（表を変えれば説明も変わる）', () => {
    const custom = { ...SOLO_KEYS, bomb: ['KeyX'] };
    expect(keyHelpFor('1P', custom).lines[1]).toBe('ばくだん X');
  });
});

describe('遊び方の説明', () => {
  it('とくぎの長押しの長さと、ポン押しの通常技が無い動物を、能力の表から出す', () => {
    const lines = describeManual().find((section) => section.title === '技ととくぎ')?.lines ?? [];
    const lineOf = (name: string): string => lines.find((line) => line.includes(name)) ?? '';
    expect(lineOf('うさぎ')).toContain('0.5 秒');
    expect(lineOf('うさぎ')).not.toContain('通常技は無い');
    expect(lineOf('ぞう')).toContain('1.5 秒');
    expect(lineOf('ぞう')).toContain('通常技は無い');
    expect(lineOf('もぐら')).toContain('通常技は無い');
  });
});

describe('メニューの動かし方の説明', () => {
  it('メニューの操作の表から作り、遊び方の説明にも出す', () => {
    const line = '↑ ← ↓ → で選び、Enter・Space で決める。Escape・Backspace で1つ前の画面へ（マウスでも押せる）';
    expect(menuHelp()).toBe(line);
    expect(describeManual().find((section) => section.title === 'メニュー')?.lines).toEqual([line]);
  });
});
