import { describe, expect, it, vi } from 'vitest';

import {
  GamepadInputSource,
  PadChoice,
  PadMenuInput,
  readBrowserGamepads,
  type PadSnapshot,
} from '../../src/platform/GamepadInput.js';
import {
  KeyboardInputSource,
  PLAYER1_KEYS,
  PLAYER2_KEYS,
  SOLO_KEYS,
  type KeyStateReader,
} from '../../src/platform/Keyboard.js';

/** 押されているキーを固定で答える（向きも爆弾と技も同じ答え）。 */
function keys(...pressed: string[]): KeyStateReader {
  const set = new Set(pressed);
  const anyOf = (codes: readonly string[]): boolean => codes.some((code) => set.has(code));
  return { anyOf, buttonAnyOf: anyOf };
}

/** 標準の並びに沿ったパッドを1つ作る。`values` はボタンごとのアナログの値（`pressed` は立てない）。 */
function pad(options: {
  index?: number;
  buttons?: number[];
  values?: Readonly<Record<number, number>>;
  axes?: number[];
  mapping?: string;
  connected?: boolean;
}): PadSnapshot {
  const held = new Set(options.buttons ?? []);
  return {
    mapping: options.mapping ?? 'standard',
    connected: options.connected ?? true,
    index: options.index ?? 0,
    buttons: Array.from({ length: 17 }, (_, i) => {
      const value = options.values?.[i];
      return value === undefined ? { pressed: held.has(i) } : { pressed: held.has(i), value };
    }),
    axes: options.axes ?? [0, 0, 0, 0],
  };
}

describe('キーボード', () => {
  it('押しているキーが入力になる', () => {
    const source = new KeyboardInputSource(0, keys('KeyD', 'Space'), PLAYER1_KEYS);
    const playerInput = source.next();
    expect(playerInput.right).toBe(true);
    expect(playerInput.bomb).toBe(true);
    expect(playerInput.left).toBe(false);
  });

  it('割り当ての中のどれを押しても同じ操作になる', () => {
    // 1P の爆弾は Space と Z の2つ。移動をどちらの手でやっても
    // 反対の手で押せるようにしてある。
    expect(new KeyboardInputSource(0, keys('Space'), PLAYER1_KEYS).next().bomb).toBe(true);
    expect(new KeyboardInputSource(0, keys('KeyZ'), PLAYER1_KEYS).next().bomb).toBe(true);
  });

  it('キーを押していなければ、何も押していない入力になる', () => {
    const playerInput = new KeyboardInputSource(0, keys(), PLAYER1_KEYS).next();
    expect(Object.values(playerInput).every((value) => value === false)).toBe(true);
  });

  it('向きは押しているキーで、爆弾と技は爆弾と技のボタンとしての押し（押した瞬間を含む）で読む', () => {
    // 向きと爆弾・技で、読む口が違う（Option・Command を離したあとに繰り返しで戻ったキーは、向きにだけ数える）。
    const reader: KeyStateReader = {
      anyOf: (codes) => codes.includes('KeyD') || codes.includes('Space') || codes.includes('KeyE'),
      buttonAnyOf: (codes) => codes.includes('KeyA'),
    };
    expect(new KeyboardInputSource(0, reader, SOLO_KEYS).next()).toEqual({
      up: false,
      down: false,
      left: false,
      right: true,
      bomb: false,
      action: false,
      special: false,
    });
    const tapped: KeyStateReader = { anyOf: () => false, buttonAnyOf: (codes) => codes.includes('Space') || codes.includes('KeyQ') };
    expect(new KeyboardInputSource(0, tapped, SOLO_KEYS).next()).toMatchObject({ bomb: true, action: true, up: false });
  });

  it('割り当ては原型の CONTROLS と同じ（J・K・X・C・R・M・N・Option も割り当てる）', () => {
    expect(SOLO_KEYS).toEqual({
      up: ['KeyW', 'ArrowUp'],
      down: ['KeyS', 'ArrowDown'],
      left: ['KeyA', 'ArrowLeft'],
      right: ['KeyD', 'ArrowRight'],
      bomb: ['Space', 'Enter', 'KeyZ', 'Slash', 'KeyJ'],
      action: ['KeyE', 'KeyQ', 'KeyX', 'KeyC', 'KeyR', 'KeyK', 'ShiftLeft', 'ShiftRight', 'Period', 'Comma', 'AltLeft', 'AltRight'],
    });
    expect(PLAYER1_KEYS).toEqual({
      up: ['KeyW'],
      down: ['KeyS'],
      left: ['KeyA'],
      right: ['KeyD'],
      bomb: ['Space', 'KeyZ'],
      action: ['KeyE', 'KeyQ', 'KeyX', 'KeyC', 'KeyR', 'ShiftLeft', 'AltLeft'],
    });
    expect(PLAYER2_KEYS).toEqual({
      up: ['ArrowUp'],
      down: ['ArrowDown'],
      left: ['ArrowLeft'],
      right: ['ArrowRight'],
      bomb: ['Enter', 'Slash'],
      action: ['ShiftRight', 'Period', 'Comma', 'KeyM', 'KeyN', 'AltRight'],
    });
    // ⛔ Command はどの組にも割り当てない（cmd+W でタブが閉じる）。
    for (const binding of [SOLO_KEYS, PLAYER1_KEYS, PLAYER2_KEYS]) {
      expect(Object.values(binding).flat().some((code) => code.startsWith('Meta'))).toBe(false);
    }
  });
});

describe('ゲームパッド', () => {
  it('十字キーで動く', () => {
    const source = new GamepadInputSource(0, new PadChoice(() => [pad({ buttons: [15] })]));
    expect(source.next().right).toBe(true);
  });

  it('A ボタンで爆弾', () => {
    const source = new GamepadInputSource(0, new PadChoice(() => [pad({ buttons: [0] })]));
    expect(source.next().bomb).toBe(true);
  });

  it('先頭が空いていても、繋がっているパッドを見つける', () => {
    // 実機では2番目に入っていた。番号を決め打ちにしない。
    const source = new GamepadInputSource(0, new PadChoice(() => [null, pad({ index: 1, buttons: [0] })]));
    expect(source.next().bomb).toBe(true);
  });

  it('標準の並びでないパッドは使わない', () => {
    const source = new GamepadInputSource(0, new PadChoice(() => [pad({ mapping: '', buttons: [0] })]));
    expect(source.next().bomb).toBe(false);
  });

  it('繋がっていなければ何も押していない入力になる', () => {
    const source = new GamepadInputSource(0, new PadChoice(() => []));
    const playerInput = source.next();
    expect(Object.values(playerInput).every((value) => value === false)).toBe(true);
  });

  it('つかんだパッドを試合中に変えない', () => {
    // 途中で別のパッドが目を覚ますと、選択が静かに移ってしまう。
    let pads: (PadSnapshot | null)[] = [pad({ index: 1, buttons: [0] })];
    const source = new GamepadInputSource(0, new PadChoice(() => pads));
    expect(source.next().bomb).toBe(true);
    pads = [pad({ index: 0, buttons: [1] }), pad({ index: 1, buttons: [0] })];
    const playerInput = source.next();
    expect(playerInput.bomb).toBe(true); // 1番のパッドを見続けている
    expect(playerInput.action).toBe(false);
  });

  it('スティックは傾きの大きい軸だけを採る', () => {
    // 軸ごとに独立して判定すると、真上から少し倒しただけで
    // 縦横の両方がしきい値を超え、横が優先されて別の向きに歩く。
    const source = new GamepadInputSource(0, new PadChoice(() => [pad({ axes: [0.6, -0.9, 0, 0] })]));
    const playerInput = source.next();
    expect(playerInput.up).toBe(true);
    expect(playerInput.right).toBe(false);
  });

  it('わずかな傾きでは動かない', () => {
    const source = new GamepadInputSource(0, new PadChoice(() => [pad({ axes: [0.2, 0, 0, 0] })]));
    expect(source.next().right).toBe(false);
  });

  it('倒したあとは戻りのしきい値まで押した扱いが続く', () => {
    // 境目でちらつかないよう、倒すときと戻すときでしきい値を分けている。
    let axes = [0.6, 0, 0, 0];
    const source = new GamepadInputSource(0, new PadChoice(() => [pad({ axes })]));
    expect(source.next().right).toBe(true);
    axes = [0.4, 0, 0, 0];
    expect(source.next().right).toBe(true);
    axes = [0.3, 0, 0, 0];
    expect(source.next().right).toBe(false);
  });

  it('pressed が立っていなくても、value が 0.5 を超えていれば押したとみなす（原型の padDown）', () => {
    // pressed が立つしきい値はブラウザの実装ごとに違う。アナログの値で届くボタンも受ける。
    expect(new GamepadInputSource(0, new PadChoice(() => [pad({ values: { 0: 0.8 } })])).next().bomb).toBe(true);
    expect(new GamepadInputSource(0, new PadChoice(() => [pad({ values: { 2: 0.51 } })])).next().action).toBe(true);
    // 0.5 ちょうどと、それより小さい値は押していない（超えたときだけ）。
    expect(new GamepadInputSource(0, new PadChoice(() => [pad({ values: { 0: 0.5 } })])).next().bomb).toBe(false);
    expect(new GamepadInputSource(0, new PadChoice(() => [pad({ values: { 0: 0.3 } })])).next().bomb).toBe(false);
  });

  it('前に読んだときに押して、もう離した爆弾と技のボタンも、忘れるまでは押したことにする', () => {
    // 試合が tick を進めないフレームに押して離したボタンを、次に進めた tick で読む（原型の pressed）。
    let current = pad({ buttons: [0, 3] });
    const choice = new PadChoice(() => [current]);
    const source = new GamepadInputSource(0, choice);
    // メニューの操作が描くたびに読む（ここで押した瞬間が残る）。
    new PadMenuInput(choice).poll();
    current = pad({});
    expect(source.next()).toMatchObject({ bomb: true, action: true });
    choice.forgetTaps();
    expect(source.next()).toMatchObject({ bomb: false, action: false });
  });

  it('押したままのボタンは、忘れたあとに読んでも、新しい押した瞬間にしない', () => {
    let current = pad({ buttons: [0] });
    const choice = new PadChoice(() => [current]);
    choice.pick();
    choice.forgetTaps();
    choice.pick();
    // 押したままなので、新しい押した瞬間は無い。
    expect(choice.tapped(0)).toBe(false);
    current = pad({});
    choice.pick();
    current = pad({ buttons: [0] });
    choice.pick();
    expect(choice.tapped(0)).toBe(true);
  });

  it('向きは押した瞬間を残さない（押してすぐ離した十字では動かない。原型と同じ）', () => {
    let current = pad({ buttons: [15] });
    const choice = new PadChoice(() => [current]);
    const source = new GamepadInputSource(0, choice);
    choice.pick();
    current = pad({});
    expect(source.next().right).toBe(false);
  });

  it('覚えた番号のパッドでも、標準の並びでなくなったら使わない（原型の pickPad）', () => {
    let pads: (PadSnapshot | null)[] = [pad({ index: 1, buttons: [0] })];
    const source = new GamepadInputSource(0, new PadChoice(() => pads));
    expect(source.next().bomb).toBe(true);
    pads = [pad({ index: 1, mapping: '', buttons: [0] })];
    expect(source.next().bomb).toBe(false);
  });
});

describe('ゲームパッドでメニューを動かす', () => {
  /** 読むたびに、いま渡されているパッドを返す。 */
  function reader(): { read: () => readonly (PadSnapshot | null)[]; set: (next: PadSnapshot | null) => void } {
    let current: PadSnapshot | null = null;
    return { read: () => [current], set: (next) => (current = next) };
  }

  it('十字キーを押した瞬間だけ、1回ずつ操作になる', () => {
    const { read, set } = reader();
    const input = new PadMenuInput(new PadChoice(read));
    set(pad({ buttons: [13] }));
    expect(input.poll()).toEqual(['down']);
    // 押したままでは続けて動かない。
    expect(input.poll()).toEqual([]);
    set(pad({}));
    expect(input.poll()).toEqual([]);
    set(pad({ buttons: [13] }));
    expect(input.poll()).toEqual(['down']);
  });

  it('A で決め、B で戻る。スティックは傾きの大きい軸の向きだけを採る', () => {
    const { read, set } = reader();
    const input = new PadMenuInput(new PadChoice(read));
    set(pad({ buttons: [0] }));
    expect(input.poll()).toEqual(['confirm']);
    set(pad({ buttons: [1] }));
    expect(input.poll()).toEqual(['back']);
    set(pad({ axes: [0.9, 0.6, 0, 0] }));
    expect(input.poll()).toEqual(['right']);
  });

  it('標準の並びでないパッドは使わない', () => {
    const { read, set } = reader();
    const input = new PadMenuInput(new PadChoice(read));
    set(pad({ mapping: '', buttons: [0, 13] }));
    expect(input.poll()).toEqual([]);
  });

  it('Start・Select と、ほかのボタン（X・Y・L1・R1・L2・R2）も、押し始めを操作として返す。L3・R3 は返さない', () => {
    // 原型はパッドのどのボタンの押し始めもメニューのカーソルへ渡す（枠が出ていなければ枠が出る）。
    const { read, set } = reader();
    const input = new PadMenuInput(new PadChoice(read));
    const startOf = (button: number): string[] => {
      set(pad({}));
      input.poll();
      set(pad({ buttons: [button] }));
      return input.poll();
    };
    expect(startOf(9)).toEqual(['start']);
    expect(startOf(8)).toEqual(['select']);
    for (const button of [2, 3, 4, 5, 6, 7]) expect(startOf(button), String(button)).toEqual(['other']);
    for (const button of [10, 11, 16]) expect(startOf(button), String(button)).toEqual([]);
    // アナログの値で届くボタン（L2・R2 のトリガ）も、0.5 を超えたら押し始め。
    set(pad({}));
    input.poll();
    set(pad({ values: { 7: 0.9 } }));
    expect(input.poll()).toEqual(['other']);
  });

  it('同じ回に押し始めたボタンは、まとめて1回で返す', () => {
    const { read, set } = reader();
    const input = new PadMenuInput(new PadChoice(read));
    set(pad({ buttons: [0, 13, 15] }));
    expect([...input.poll()].sort()).toEqual(['confirm', 'down', 'right']);
    // 押したままの A と十字に B を足すと、B だけが押し始め。
    set(pad({ buttons: [0, 1, 13, 15] }));
    expect(input.poll()).toEqual(['back']);
  });

  it('枠を出すだけのボタンは、ボタンごとに押し始めを見る（X を押したまま Y を押し始めても返す。原型と同じ）', () => {
    const { read, set } = reader();
    const input = new PadMenuInput(new PadChoice(read));
    set(pad({ buttons: [2] }));
    expect(input.poll()).toEqual(['other']);
    set(pad({ buttons: [2, 3] }));
    expect(input.poll()).toEqual(['other']);
    // 押したままでは続けて返さない。
    expect(input.poll()).toEqual([]);
    // 1つ離しても押し始めにはならない。
    set(pad({ buttons: [3] }));
    expect(input.poll()).toEqual([]);
  });
});

describe('つかむパッド', () => {
  it('メニューと試合で1つを分け合い、あとから別のパッドが点いても移らない', () => {
    // 読む側ごとに番号を覚えると、メニューで1番をつかんだあと、試合の側が先頭から探し直して
    // 0番をつかむ。手元の1番では操作できなくなる（原型も番号を1つだけ持っていた）。
    let first: PadSnapshot | null = null;
    const second = pad({ index: 1, buttons: [0] });
    const choice = new PadChoice(() => [first, second]);
    expect(new PadMenuInput(choice).poll()).toEqual(['confirm']);
    first = pad({ index: 0 });
    expect(new GamepadInputSource(0, choice).next().bomb).toBe(true);
  });

  it('見つけたことと、標準の並びでない機器のことを、それぞれ1回だけ知らせる（原型の PAD.announced・PAD.warned）', () => {
    let pads: (PadSnapshot | null)[] = [];
    const choice = new PadChoice(() => pads);
    choice.pick();
    expect(choice.takeNotices()).toEqual([]);
    // 標準の並びでない機器だけ：名前を添えて知らせる。見つけてはいない。
    pads = [{ ...pad({ index: 0, mapping: '' }), id: 'Odd Stick' }];
    choice.pick();
    choice.pick();
    expect(choice.takeNotices()).toEqual([{ kind: 'unsupported', id: 'Odd Stick' }]);
    expect(choice.takeNotices()).toEqual([]);
    // 標準のパッドが点いたら、見つけたことを1回だけ知らせる。対応していない機器のことは、もう知らせない。
    pads = [{ ...pad({ index: 0, mapping: '' }), id: 'Odd Stick' }, pad({ index: 1 })];
    choice.pick();
    choice.pick();
    expect(choice.takeNotices()).toEqual([{ kind: 'found' }]);
    // 抜いて差し直しても、知らせ直さない（原型も起動の間に1回だけ）。
    pads = [];
    choice.pick();
    pads = [pad({ index: 1 })];
    choice.pick();
    expect(choice.takeNotices()).toEqual([]);
  });

  it('覚えたパッドが生きている間は探し直さないので、あとから点いた標準でない機器のことは知らせない（原型の pickPad）', () => {
    let pads: (PadSnapshot | null)[] = [pad({ index: 1 })];
    const choice = new PadChoice(() => pads);
    choice.pick();
    expect(choice.takeNotices()).toEqual([{ kind: 'found' }]);
    pads = [{ ...pad({ index: 0, mapping: '' }), id: 'Odd Stick' }, pad({ index: 1 })];
    choice.pick();
    expect(choice.takeNotices()).toEqual([]);
  });
});

describe('ブラウザからパッドを読む', () => {
  it('読み取りが例外を投げたら、パッドは無いものとして扱う', () => {
    // gamepad を許していない別オリジンの iframe などでは、getGamepads が SecurityError を投げる。
    // 描くたびに読むので、投げたままにすると描画のループが最初の1枚で止まり、どの画面も動かなくなる
    // （原型も、読み取りの例外は握りつぶしていた）。
    vi.stubGlobal('navigator', {
      getGamepads: () => {
        throw new Error('SecurityError');
      },
    });
    try {
      // 差し替えが反映されていることを先に確認する（反映されていなければ、下の確認は何も見ていない）。
      expect(() => (globalThis.navigator as unknown as { getGamepads: () => unknown }).getGamepads()).toThrow('SecurityError');
      expect(readBrowserGamepads()).toEqual([]);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('ボタンのアナログの値（value）も写す。写さないと、pressed の立たないボタンを試合で読めない', () => {
    const buttons = Array.from({ length: 17 }, (_, i) => ({ pressed: false, value: i === 0 ? 0.8 : 0 }));
    vi.stubGlobal('navigator', {
      getGamepads: () => [{ mapping: 'standard', connected: true, index: 0, buttons, axes: [0, 0, 0, 0], id: 'Pad (Vendor: 1)' }],
    });
    try {
      const [snapshot] = readBrowserGamepads();
      expect(snapshot?.buttons[0]).toEqual({ pressed: false, value: 0.8 });
      // 機器の名前も写す（対応していない機器の通知に出す）。
      expect(snapshot?.id).toBe('Pad (Vendor: 1)');
      expect(new GamepadInputSource(0, new PadChoice(readBrowserGamepads)).next().bomb).toBe(true);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
