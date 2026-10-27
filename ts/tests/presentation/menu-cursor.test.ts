import { describe, expect, it } from 'vitest';

import { navCommandOf } from '../../src/platform/Keyboard.js';
import { MenuCursor } from '../../src/presentation/menu/MenuCursor.js';

/** タイトルのような縦の3つと、横に4つ並ぶ行が1つ。 */
const SIZES = [1, 4, 1];

describe('メニューのカーソル', () => {
  it('枠が出ていないときの決定は、枠を出すだけで押さない', () => {
    const cursor = new MenuCursor();
    expect(cursor.handle(['confirm'], SIZES)).toEqual({ kind: 'moved' });
    expect(cursor.shown).toBe(true);
    expect(cursor.handle(['confirm'], SIZES)).toEqual({ kind: 'activate', group: 0, item: 0 });
  });

  it('操作を待たずに枠を出すと（幕・Select で開いた確認の画面）、次の決定は枠を出すだけにならずに押す。位置は変えない', () => {
    const cursor = new MenuCursor();
    cursor.handle(['down'], SIZES);
    cursor.hide();
    cursor.show();
    expect([cursor.shown, cursor.group, cursor.item]).toEqual([true, 1, 0]);
    expect(cursor.handle(['confirm'], SIZES)).toEqual({ kind: 'activate', group: 1, item: 0 });
  });

  it('枠が出ていないときの移動と戻るは、枠を出したうえで反映される', () => {
    // 移動まで飲み込むと、マウスに触れたあとの最初の1押しが毎回反映されない。
    const moving = new MenuCursor();
    expect(moving.handle(['down'], SIZES)).toEqual({ kind: 'moved' });
    expect([moving.shown, moving.group]).toEqual([true, 1]);
    expect(new MenuCursor().handle(['back'], SIZES)).toEqual({ kind: 'back' });
  });

  it('上下でグループを、左右でグループの中を移り、端から反対の端へ回る', () => {
    const cursor = new MenuCursor();
    cursor.handle(['up'], SIZES);
    expect(cursor.group).toBe(2);
    cursor.handle(['up'], SIZES);
    expect(cursor.group).toBe(1);
    cursor.handle(['left'], SIZES);
    expect(cursor.item).toBe(3);
    cursor.handle(['right'], SIZES);
    expect(cursor.item).toBe(0);
    expect(cursor.handle(['confirm'], SIZES)).toEqual({ kind: 'activate', group: 1, item: 0 });
  });

  it('項目の少ないグループへ移ると、項目の番号を中へ丸める', () => {
    const cursor = new MenuCursor();
    cursor.handle(['down'], SIZES);
    cursor.handle(['left'], SIZES);
    expect([cursor.group, cursor.item]).toEqual([1, 3]);
    cursor.handle(['down'], SIZES);
    expect([cursor.group, cursor.item]).toEqual([2, 0]);
  });

  it('項目が減っていたら、次の操作の前に中へ丸める', () => {
    const cursor = new MenuCursor();
    cursor.handle(['down'], SIZES);
    cursor.handle(['left'], SIZES);
    expect(cursor.handle(['confirm'], [1, 2])).toEqual({ kind: 'activate', group: 1, item: 1 });
  });

  it('並びが空なら、戻るも含めて何もしない', () => {
    // 試合の最中（幕にボタンが無い）に、矢印や Escape で何かが起きないように。
    const cursor = new MenuCursor();
    for (const command of ['up', 'confirm', 'back'] as const) {
      expect(cursor.handle([command], [])).toEqual({ kind: 'none' });
    }
    expect(cursor.shown).toBe(false);
  });

  it('枠を消すと、次の決定はまた枠を出すだけになる。先頭へ戻すと位置だけが戻る', () => {
    const cursor = new MenuCursor();
    cursor.handle(['down'], SIZES);
    cursor.hide();
    expect(cursor.handle(['confirm'], SIZES)).toEqual({ kind: 'moved' });
    cursor.reset();
    expect([cursor.shown, cursor.group, cursor.item]).toEqual([true, 0, 0]);
  });
});

describe('1回にまとめて届く操作（原型の MENU.nav。L3288-3322）', () => {
  it('枠が出ていないとき、決定が含まれていれば、同じ回の移動も飲み込んで枠を出すだけ', () => {
    const cursor = new MenuCursor();
    expect(cursor.handle(['down', 'right', 'confirm'], SIZES)).toEqual({ kind: 'moved' });
    expect([cursor.shown, cursor.group, cursor.item]).toEqual([true, 0, 0]);
  });

  it('枠が出ていないとき、決定が無ければ、枠を出したうえで上下と左右を同じ回に動かす', () => {
    const cursor = new MenuCursor();
    expect(cursor.handle(['down', 'right'], SIZES)).toEqual({ kind: 'moved' });
    expect([cursor.group, cursor.item]).toEqual([1, 1]);
  });

  it('戻るがあれば戻るだけ（決定も移動もしない）', () => {
    const cursor = new MenuCursor();
    cursor.handle(['down'], SIZES);
    expect(cursor.handle(['confirm', 'back', 'down'], SIZES)).toEqual({ kind: 'back' });
    expect(cursor.group).toBe(1);
  });

  it('決定があれば決定だけ（同じ回の移動はしない）', () => {
    const cursor = new MenuCursor();
    cursor.handle(['down'], SIZES);
    expect(cursor.handle(['right', 'confirm', 'down'], SIZES)).toEqual({ kind: 'activate', group: 1, item: 0 });
    expect([cursor.group, cursor.item]).toEqual([1, 0]);
  });

  it('上下は下を、左右は右を先に見る（原型の else if の順）', () => {
    const cursor = new MenuCursor();
    cursor.handle(['down'], SIZES);
    cursor.handle(['left', 'right'], SIZES);
    expect([cursor.group, cursor.item]).toEqual([1, 1]);
    cursor.handle(['up', 'down'], SIZES);
    expect([cursor.group, cursor.item]).toEqual([2, 0]);
  });

  it('上下で移った先のグループで、同じ回の左右を数える（項目の数もその行で丸める）', () => {
    const cursor = new MenuCursor();
    cursor.handle(['left'], SIZES);
    // 先頭の行（1つ）から下の行（4つ）へ移り、その行で右へ1つ。
    cursor.handle(['down', 'right'], SIZES);
    expect([cursor.group, cursor.item]).toEqual([1, 1]);

    // 項目の多い行（4つ）の端から少ない行（3つ）へ移ると、丸めてから右へ回る（原型 L3315）。
    const narrowing = new MenuCursor();
    narrowing.handle(['left'], [4, 3]);
    expect([narrowing.group, narrowing.item]).toEqual([0, 3]);
    narrowing.handle(['down', 'right'], [4, 3]);
    expect([narrowing.group, narrowing.item]).toEqual([1, 0]);
  });

  it('Start・Select・ほかのボタンは、枠が出ていなければ枠を出すだけ。出ていれば何もしない', () => {
    for (const command of ['start', 'select', 'other'] as const) {
      const cursor = new MenuCursor();
      expect(cursor.handle([command], SIZES), command).toEqual({ kind: 'moved' });
      expect([cursor.shown, cursor.group, cursor.item], command).toEqual([true, 0, 0]);
      expect(cursor.handle([command], SIZES), command).toEqual({ kind: 'none' });
      expect([cursor.group, cursor.item], command).toEqual([0, 0]);
    }
  });

  it('何も届かなければ、枠も出さない', () => {
    const cursor = new MenuCursor();
    expect(cursor.handle([], SIZES)).toEqual({ kind: 'none' });
    expect(cursor.shown).toBe(false);
  });
});

describe('キーからメニューの操作への翻訳', () => {
  const key = (code: string, extra: { repeat?: boolean } = {}) => ({ code, repeat: false, ...extra });

  it('矢印で動かし、Enter と Space で決め、Escape と Backspace で戻る（原型と同じ）', () => {
    const codes = ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Enter', 'Space', 'Escape', 'Backspace'];
    expect(codes.map((code) => navCommandOf(key(code)))).toEqual([
      'up', 'down', 'left', 'right', 'confirm', 'confirm', 'back', 'back',
    ]);
  });

  it('押し続けたときの繰り返しと、ほかのキーは数えない。修飾キーは見ない（原型と同じ）', () => {
    expect(navCommandOf(key('ArrowDown', { repeat: true }))).toBeNull();
    expect(navCommandOf(key('KeyW'))).toBeNull();
    // Command・Ctrl・Option と一緒でも数える（原型の keydown は修飾キーを見ない。L3062-3068）。
    for (const modifier of ['metaKey', 'ctrlKey', 'altKey', 'shiftKey'] as const) {
      const event = { ...key('Enter'), [modifier]: true };
      expect(navCommandOf(event), modifier).toBe('confirm');
    }
  });
});
