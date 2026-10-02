import { describe, expect, it } from 'vitest';

import { IDLE_INPUT, type PlayerInput } from '../../src/domain/input/PlayerInput.js';
import type { PlayerId } from '../../src/domain/state/PlayerState.js';
import { CombinedInputSource } from '../../src/platform/CombinedInputSource.js';
import { GamepadInputSource, PadChoice, type PadSnapshot } from '../../src/platform/GamepadInput.js';
import { KeyboardInputSource, SOLO_KEYS } from '../../src/platform/Keyboard.js';
import { makeWorld } from '../helpers.js';

function fixed(playerId: PlayerId, playerInput: Partial<PlayerInput>): { playerId: PlayerId; next: () => PlayerInput; reads: number } {
  const source = {
    playerId,
    reads: 0,
    next: (): PlayerInput => {
      source.reads += 1;
      return { ...IDLE_INPUT, ...playerInput };
    },
  };
  return source;
}

describe('キーボードとゲームパッドをまとめる', () => {
  it('どちらかで押していれば押している', () => {
    const combined = new CombinedInputSource([fixed(0, { up: true }), fixed(0, { bomb: true })]);
    expect(combined.next(makeWorld())).toEqual({ ...IDLE_INPUT, up: true, bomb: true });
  });

  it('毎回すべての機器を読む（途中で打ち切らない）', () => {
    const first = fixed(0, { up: true });
    const second = fixed(0, {});
    const combined = new CombinedInputSource([first, second]);
    combined.next(makeWorld());
    expect([first.reads, second.reads]).toEqual([1, 1]);
  });

  it('別のプレイヤーの窓口や、空の並びは受け付けない', () => {
    expect(() => new CombinedInputSource([fixed(0, {}), fixed(1, {})])).toThrow('別のプレイヤー');
    expect(() => new CombinedInputSource([])).toThrow('窓口が無い');
  });

  it('実物のキーボードとパッドの窓口をまとめられる', () => {
    const pad: PadSnapshot = {
      mapping: 'standard',
      connected: true,
      index: 0,
      buttons: Array.from({ length: 17 }, (_, i) => ({ pressed: i === 0 })),
      axes: [0, 0, 0, 0],
    };
    const keyboard = new KeyboardInputSource(0, { anyOf: (codes) => codes.includes('KeyD') }, SOLO_KEYS);
    const gamepad = new GamepadInputSource(0, new PadChoice(() => [pad]));
    const playerInput = new CombinedInputSource([keyboard, gamepad]).next(makeWorld());
    expect(playerInput).toMatchObject({ right: true, bomb: true, up: false });
  });
});
