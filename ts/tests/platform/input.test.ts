import { describe, expect, it } from 'vitest';

import {
  GamepadIntentSource,
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
    const source = new GamepadIntentSource(0, () => [pad({ buttons: [15] })]);
    expect(source.next().right).toBe(true);
  });

  it('A ボタンで爆弾', () => {
    const source = new GamepadIntentSource(0, () => [pad({ buttons: [0] })]);
    expect(source.next().bomb).toBe(true);
  });

  it('先頭が空いていても、繋がっているパッドを見つける', () => {
    // 実機では2番目に入っていた。番号を決め打ちにしない。
    const source = new GamepadIntentSource(0, () => [null, pad({ index: 1, buttons: [0] })]);
    expect(source.next().bomb).toBe(true);
  });

  it('標準の並びでないパッドは使わない', () => {
    const source = new GamepadIntentSource(0, () => [pad({ mapping: '', buttons: [0] })]);
    expect(source.next().bomb).toBe(false);
  });

  it('繋がっていなければ何もしない意思になる', () => {
    const source = new GamepadIntentSource(0, () => []);
    const intent = source.next();
    expect(Object.values(intent).every((value) => value === false)).toBe(true);
  });

  it('つかんだパッドを試合中に変えない', () => {
    // 途中で別のパッドが目を覚ますと、選択が静かに移ってしまう。
    let pads: (PadSnapshot | null)[] = [pad({ index: 1, buttons: [0] })];
    const source = new GamepadIntentSource(0, () => pads);
    expect(source.next().bomb).toBe(true);
    pads = [pad({ index: 0, buttons: [1] }), pad({ index: 1, buttons: [0] })];
    const intent = source.next();
    expect(intent.bomb).toBe(true); // 1番のパッドを見続けている
    expect(intent.action).toBe(false);
  });

  it('スティックは傾きの大きい軸だけを採る', () => {
    // 軸ごとに独立して判定すると、真上から少し倒しただけで
    // 縦横の両方がしきい値を超え、横が優先されて別の向きに歩く。
    const source = new GamepadIntentSource(0, () => [pad({ axes: [0.6, -0.9, 0, 0] })]);
    const intent = source.next();
    expect(intent.up).toBe(true);
    expect(intent.right).toBe(false);
  });

  it('わずかな傾きでは動かない', () => {
    const source = new GamepadIntentSource(0, () => [pad({ axes: [0.2, 0, 0, 0] })]);
    expect(source.next().right).toBe(false);
  });

  it('倒したあとは戻りのしきい値まで効き続ける', () => {
    // 境目でちらつかないよう、倒すときと戻すときでしきい値を分けている。
    let axes = [0.6, 0, 0, 0];
    const source = new GamepadIntentSource(0, () => [pad({ axes })]);
    expect(source.next().right).toBe(true);
    axes = [0.4, 0, 0, 0];
    expect(source.next().right).toBe(true);
    axes = [0.3, 0, 0, 0];
    expect(source.next().right).toBe(false);
  });
});
