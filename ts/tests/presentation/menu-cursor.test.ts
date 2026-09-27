import { describe, expect, it } from 'vitest';

import { navCommandOf } from '../../src/platform/Keyboard.js';
import { MenuCursor } from '../../src/presentation/menu/MenuCursor.js';

/** タイトルのような縦の3つと、横に4つ並ぶ行が1つ。 */
const SIZES = [1, 4, 1];

describe('メニューのカーソル', () => {
  it('枠が出ていないときの決定は、枠を出すだけで押さない', () => {
    const cursor = new MenuCursor();
    expect(cursor.handle('confirm', SIZES)).toEqual({ kind: 'moved' });
    expect(cursor.shown).toBe(true);
    expect(cursor.handle('confirm', SIZES)).toEqual({ kind: 'activate', group: 0, item: 0 });
  });

  it('優勝の幕の扱い（activate）では、枠が出ていないときの決定も、枠を出してそのまま押す', () => {
    const cursor = new MenuCursor();
    expect(cursor.handle('confirm', SIZES, 'activate')).toEqual({ kind: 'activate', group: 0, item: 0 });
    expect(cursor.shown).toBe(true);
  });

  it('枠が出ていないときの移動と戻るは、枠を出したうえで効く', () => {
    // 移動まで飲み込むと、マウスに触れたあとの最初の1押しが毎回効かない。
    const moving = new MenuCursor();
    expect(moving.handle('down', SIZES)).toEqual({ kind: 'moved' });
    expect([moving.shown, moving.group]).toEqual([true, 1]);
    expect(new MenuCursor().handle('back', SIZES)).toEqual({ kind: 'back' });
  });

  it('上下でグループを、左右でグループの中を移り、端から反対の端へ回る', () => {
    const cursor = new MenuCursor();
    cursor.handle('up', SIZES);
    expect(cursor.group).toBe(2);
    cursor.handle('up', SIZES);
    expect(cursor.group).toBe(1);
    cursor.handle('left', SIZES);
    expect(cursor.item).toBe(3);
    cursor.handle('right', SIZES);
    expect(cursor.item).toBe(0);
    expect(cursor.handle('confirm', SIZES)).toEqual({ kind: 'activate', group: 1, item: 0 });
  });

  it('項目の少ないグループへ移ると、項目の番号を中へ丸める', () => {
    const cursor = new MenuCursor();
    cursor.handle('down', SIZES);
    cursor.handle('left', SIZES);
    expect([cursor.group, cursor.item]).toEqual([1, 3]);
    cursor.handle('down', SIZES);
    expect([cursor.group, cursor.item]).toEqual([2, 0]);
  });

  it('項目が減っていたら、次の操作の前に中へ丸める', () => {
    const cursor = new MenuCursor();
    cursor.handle('down', SIZES);
    cursor.handle('left', SIZES);
    expect(cursor.handle('confirm', [1, 2])).toEqual({ kind: 'activate', group: 1, item: 1 });
  });

  it('並びが空なら、戻るも含めて何もしない', () => {
    // 試合の最中（幕にボタンが無い）に、矢印や Escape で何かが起きないように。
    const cursor = new MenuCursor();
    for (const command of ['up', 'confirm', 'back'] as const) {
      expect(cursor.handle(command, [])).toEqual({ kind: 'none' });
    }
    expect(cursor.shown).toBe(false);
  });

  it('枠を消すと、次の決定はまた枠を出すだけになる。先頭へ戻すと位置だけが戻る', () => {
    const cursor = new MenuCursor();
    cursor.handle('down', SIZES);
    cursor.hide();
    expect(cursor.handle('confirm', SIZES)).toEqual({ kind: 'moved' });
    cursor.reset();
    expect([cursor.shown, cursor.group, cursor.item]).toEqual([true, 0, 0]);
  });
});

describe('キーからメニューの操作への翻訳', () => {
  const key = (code: string, extra: Partial<KeyboardEvent> = {}) => ({
    code,
    repeat: false,
    metaKey: false,
    ctrlKey: false,
    altKey: false,
    ...extra,
  });

  it('矢印で動かし、Enter と Space で決め、Escape と Backspace で戻る（原型と同じ）', () => {
    const codes = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Enter', 'Space', 'Escape', 'Backspace'];
    expect(codes.map((code) => navCommandOf(key(code)))).toEqual([
      'up', 'down', 'left', 'right', 'confirm', 'confirm', 'back', 'back',
    ]);
  });

  it('押し続けたときの繰り返しと、Command・Ctrl・Option と一緒のときは数えない。ほかのキーも数えない', () => {
    expect(navCommandOf(key('ArrowDown', { repeat: true }))).toBeNull();
    for (const modifier of ['metaKey', 'ctrlKey', 'altKey'] as const) {
      expect(navCommandOf(key('Enter', { [modifier]: true })), modifier).toBeNull();
    }
    // Shift は技のキーでもあるが、メニューの操作には関わらない。
    expect(navCommandOf(key('ArrowUp', { shiftKey: true }))).toBe('up');
    expect(navCommandOf(key('KeyW'))).toBeNull();
  });
});
