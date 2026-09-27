import { describe, expect, it } from 'vitest';

import { lockstepUrl, parseRelayAddress } from '../../src/platform/WebSocketLink.js';

describe('?relay の値を読む', () => {
  it.each([
    ['mac.local:8777', 'mac.local:8777'],
    ['192.168.1.20:8777', '192.168.1.20:8777'],
    ['[::1]:8777', '[::1]:8777'],
    // 貼り付けで付きやすいものは取り除いて読む。
    ['  mac.local:8777  ', 'mac.local:8777'],
    ['mac.local:8777/', 'mac.local:8777'],
    ['http://mac.local:8777/', 'mac.local:8777'],
    ['ws://mac.local:8777', 'mac.local:8777'],
  ])('%s → %s', (value, expected) => {
    expect(parseRelayAddress(value)).toBe(expected);
    expect(lockstepUrl(expected)).toBe(`ws://${expected}/lockstep`);
  });

  it.each([
    ['ポートが無い', 'mac.local'],
    ['空白が混ざる', 'mac local:8777'],
    ['パスが付いている', 'mac.local:8777/lockstep'],
    ['クエリが付いている', 'mac.local:8777/?x=1'],
    ['利用者名が付いている', 'user@mac.local:8777'],
    ['空', ''],
  ])('読めないものは null: %s', (_label, value) => {
    // そのまま URL に埋めると、別の部屋や別のホストにつながる。
    expect(parseRelayAddress(value)).toBeNull();
  });
});
