// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from 'vitest';

import { GAME_KEYS, KeyboardWatcher, SOLO_KEYS } from '../../src/platform/Keyboard.js';

function keydown(code: string): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { code, cancelable: true });
  window.dispatchEvent(event);
  return event;
}

const watcher = new KeyboardWatcher();
afterEach(() => watcher.detach());

describe('試合の画面のキー', () => {
  it('止めると決めたキーだけ、ブラウザの既定の動きを止める', () => {
    watcher.attach();
    watcher.capture(GAME_KEYS);
    expect(keydown('ArrowDown').defaultPrevented).toBe(true);
    expect(keydown('Space').defaultPrevented).toBe(true);
    // ポーズのキーやほかのキーは止めない。
    expect(keydown('KeyP').defaultPrevented).toBe(false);

    watcher.capture([]);
    expect(keydown('ArrowDown').defaultPrevented).toBe(false);
  });

  it('止めても、押されたことは数える', () => {
    watcher.attach();
    watcher.capture(GAME_KEYS);
    keydown('ArrowUp');
    expect(watcher.anyOf(SOLO_KEYS.up)).toBe(true);
  });

  it('操作に使うキーは全部、止める対象に入っている', () => {
    for (const code of [...SOLO_KEYS.up, ...SOLO_KEYS.bomb, 'ShiftRight', 'Comma']) {
      expect(GAME_KEYS).toContain(code);
    }
  });
});
