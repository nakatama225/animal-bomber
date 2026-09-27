import { describe, expect, it } from 'vitest';

import { loadSound, saveSound, type PreferenceStore } from '../../src/platform/preferences.js';

function memory(): PreferenceStore & { readonly items: Map<string, string> } {
  const items = new Map<string, string>();
  return { items, getItem: (key) => items.get(key) ?? null, setItem: (key, value) => void items.set(key, value) };
}

describe('音の設定を残す', () => {
  it('残した設定を、開き直したあとに読める', () => {
    const store = memory();
    saveSound('sfx', () => store);
    expect(loadSound(() => store)).toBe('sfx');
  });

  it('残っていない・知らない値なら、既定に任せる（null）', () => {
    const store = memory();
    expect(loadSound(() => store)).toBeNull();
    store.items.set('animal-bomber.sound', 'loud');
    expect(loadSound(() => store)).toBeNull();
  });

  it('残す場所が使えなくても止まらない', () => {
    // プライベートのウィンドウなどでは、読むだけで例外になることがある。
    const broken: PreferenceStore = {
      getItem: () => {
        throw new Error('使えない');
      },
      setItem: () => {
        throw new Error('使えない');
      },
    };
    expect(loadSound(() => broken)).toBeNull();
    expect(() => saveSound('off', () => broken)).not.toThrow();
    expect(loadSound(() => null)).toBeNull();
  });
});
