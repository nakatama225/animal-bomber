import { describe, expect, it, vi } from 'vitest';

import {
  GamepadIntentSource,
  PadChoice,
  PadMenuInput,
  readBrowserGamepads,
  type PadSnapshot,
} from '../../src/platform/GamepadInput.js';
import {
  KeyboardIntentSource,
  PLAYER1_KEYS,
  type KeyStateReader,
} from '../../src/platform/Keyboard.js';

/** 押されているキーを固定で答える。 */
function keys(...pressed: string[]): KeyStateReader {
  const set = new Set(pressed);
  return { anyOf: (codes) => codes.some((code) => set.has(code)) };
}

/** 標準の並びに沿ったパッドを1つ作る。 */
function pad(options: {
  index?: number;
  buttons?: number[];
  axes?: number[];
  mapping?: string;
  connected?: boolean;
}): PadSnapshot {
  const held = new Set(options.buttons ?? []);
  return {
    mapping: options.mapping ?? 'standard',
    connected: options.connected ?? true,
    index: options.index ?? 0,
    buttons: Array.from({ length: 17 }, (_, i) => ({ pressed: held.has(i) })),
    axes: options.axes ?? [0, 0, 0, 0],
  };
}

describe('キーボード', () => {
  it('押しているキーが意思になる', () => {
    const source = new KeyboardIntentSource(0, keys('KeyD', 'Space'), PLAYER1_KEYS);
    const intent = source.next();
    expect(intent.right).toBe(true);
    expect(intent.bomb).toBe(true);
    expect(intent.left).toBe(false);
  });

  it('割り当ての中のどれを押しても同じ操作になる', () => {
    // 1P の爆弾は Space と Z の2つ。移動をどちらの手でやっても
    // 反対の手で押せるようにしてある。
    expect(new KeyboardIntentSource(0, keys('Space'), PLAYER1_KEYS).next().bomb).toBe(true);
    expect(new KeyboardIntentSource(0, keys('KeyZ'), PLAYER1_KEYS).next().bomb).toBe(true);
  });

  it('何も押していなければ何もしない意思になる', () => {
    const intent = new KeyboardIntentSource(0, keys(), PLAYER1_KEYS).next();
    expect(Object.values(intent).every((value) => value === false)).toBe(true);
  });
});

describe('ゲームパッド', () => {
  it('十字キーで動く', () => {
    const source = new GamepadIntentSource(0, new PadChoice(() => [pad({ buttons: [15] })]));
    expect(source.next().right).toBe(true);
  });

  it('A ボタンで爆弾', () => {
    const source = new GamepadIntentSource(0, new PadChoice(() => [pad({ buttons: [0] })]));
    expect(source.next().bomb).toBe(true);
  });

  it('先頭が空いていても、繋がっているパッドを見つける', () => {
    // 実機では2番目に入っていた。番号を決め打ちにしない。
    const source = new GamepadIntentSource(0, new PadChoice(() => [null, pad({ index: 1, buttons: [0] })]));
    expect(source.next().bomb).toBe(true);
  });

  it('標準の並びでないパッドは使わない', () => {
    const source = new GamepadIntentSource(0, new PadChoice(() => [pad({ mapping: '', buttons: [0] })]));
    expect(source.next().bomb).toBe(false);
  });

  it('繋がっていなければ何もしない意思になる', () => {
    const source = new GamepadIntentSource(0, new PadChoice(() => []));
    const intent = source.next();
    expect(Object.values(intent).every((value) => value === false)).toBe(true);
  });

  it('つかんだパッドを試合中に変えない', () => {
    // 途中で別のパッドが目を覚ますと、選択が静かに移ってしまう。
    let pads: (PadSnapshot | null)[] = [pad({ index: 1, buttons: [0] })];
    const source = new GamepadIntentSource(0, new PadChoice(() => pads));
    expect(source.next().bomb).toBe(true);
    pads = [pad({ index: 0, buttons: [1] }), pad({ index: 1, buttons: [0] })];
    const intent = source.next();
    expect(intent.bomb).toBe(true); // 1番のパッドを見続けている
    expect(intent.action).toBe(false);
  });

  it('スティックは傾きの大きい軸だけを採る', () => {
    // 軸ごとに独立して判定すると、真上から少し倒しただけで
    // 縦横の両方がしきい値を超え、横が優先されて別の向きに歩く。
    const source = new GamepadIntentSource(0, new PadChoice(() => [pad({ axes: [0.6, -0.9, 0, 0] })]));
    const intent = source.next();
    expect(intent.up).toBe(true);
    expect(intent.right).toBe(false);
  });

  it('わずかな傾きでは動かない', () => {
    const source = new GamepadIntentSource(0, new PadChoice(() => [pad({ axes: [0.2, 0, 0, 0] })]));
    expect(source.next().right).toBe(false);
  });

  it('倒したあとは戻りのしきい値まで効き続ける', () => {
    // 境目でちらつかないよう、倒すときと戻すときでしきい値を分けている。
    let axes = [0.6, 0, 0, 0];
    const source = new GamepadIntentSource(0, new PadChoice(() => [pad({ axes })]));
    expect(source.next().right).toBe(true);
    axes = [0.4, 0, 0, 0];
    expect(source.next().right).toBe(true);
    axes = [0.3, 0, 0, 0];
    expect(source.next().right).toBe(false);
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
    expect(new GamepadIntentSource(0, choice).next().bomb).toBe(true);
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
      // 差し替えが効いていることを先に確かめる（効いていなければ、下の確かめは何も見ていない）。
      expect(() => (globalThis.navigator as unknown as { getGamepads: () => unknown }).getGamepads()).toThrow('SecurityError');
      expect(readBrowserGamepads()).toEqual([]);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
