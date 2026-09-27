import { describe, expect, it } from 'vitest';

import { IDLE_INTENT, type PlayerIntent } from '../../src/domain/intent/PlayerIntent.js';
import type { PlayerId } from '../../src/domain/state/PlayerState.js';
import { CombinedIntentSource } from '../../src/platform/CombinedIntentSource.js';
import { GamepadIntentSource, type PadSnapshot } from '../../src/platform/GamepadInput.js';
import { KeyboardIntentSource, SOLO_KEYS } from '../../src/platform/Keyboard.js';
import { makeWorld } from '../helpers.js';

function fixed(playerId: PlayerId, intent: Partial<PlayerIntent>): { playerId: PlayerId; next: () => PlayerIntent; reads: number } {
  const source = {
    playerId,
    reads: 0,
    next: (): PlayerIntent => {
      source.reads += 1;
      return { ...IDLE_INTENT, ...intent };
    },
  };
  return source;
}

describe('キーボードとゲームパッドをまとめる', () => {
  it('どちらかで押していれば押している', () => {
    const combined = new CombinedIntentSource([fixed(0, { up: true }), fixed(0, { bomb: true })]);
    expect(combined.next(makeWorld())).toEqual({ ...IDLE_INTENT, up: true, bomb: true });
  });

  it('毎回すべての機器を読む（途中で打ち切らない）', () => {
    const first = fixed(0, { up: true });
    const second = fixed(0, {});
    const combined = new CombinedIntentSource([first, second]);
    combined.next(makeWorld());
    expect([first.reads, second.reads]).toEqual([1, 1]);
  });

  it('別のプレイヤーの窓口や、空の並びは受け付けない', () => {
    expect(() => new CombinedIntentSource([fixed(0, {}), fixed(1, {})])).toThrow('別のプレイヤー');
    expect(() => new CombinedIntentSource([])).toThrow('窓口が無い');
  });

  it('実物のキーボードとパッドの窓口をまとめられる', () => {
    const pad: PadSnapshot = {
      mapping: 'standard',
      connected: true,
      index: 0,
      buttons: Array.from({ length: 17 }, (_, i) => ({ pressed: i === 0 })),
      axes: [0, 0, 0, 0],
    };
    const keyboard = new KeyboardIntentSource(0, { anyOf: (codes) => codes.includes('KeyD') }, SOLO_KEYS);
    const gamepad = new GamepadIntentSource(0, () => [pad]);
    const intent = new CombinedIntentSource([keyboard, gamepad]).next(makeWorld());
    expect(intent).toMatchObject({ right: true, bomb: true, up: false });
  });
});
