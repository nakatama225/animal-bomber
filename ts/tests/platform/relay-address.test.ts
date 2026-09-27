import { describe, expect, it } from 'vitest';

import { defaultRelayAddress, lockstepUrl, parseRelayAddress } from '../../src/platform/WebSocketLink.js';

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

describe('?relay の値を省いたときの中継', () => {
  it('中継から /ts/ の下で配られたページなら、ページと同じ端末・同じポートの中継につなぐ', () => {
    // 中継を --port 9000 で立てると、ページも 9000 番から届く。8777 番に決め打ちすると、
    // そこにいない中継（または別の中継）につなぎにいく。
    expect(defaultRelayAddress({ pathname: '/ts/', hostname: 'mac.local', port: '9000' })).toBe('mac.local:9000');
    expect(defaultRelayAddress({ pathname: '/ts/index.html', hostname: 'mac.local', port: '8777' })).toBe('mac.local:8777');
  });

  it('開発サーバから開いたページは、同じ端末の 8777 番の中継につなぐ', () => {
    expect(defaultRelayAddress({ pathname: '/', hostname: 'mac.local', port: '5173' })).toBe('mac.local:8777');
  });

  it('ポートの無い URL（80 番）で配られたページは、これまでどおり 8777 番につなぐ', () => {
    // 中継を 80 番で立てることは想定しない。`ws://…:80` は既定のポートとして省かれ、読めない値になる。
    const address = defaultRelayAddress({ pathname: '/ts/', hostname: 'mac.local', port: '' });
    expect(address).toBe('mac.local:8777');
    expect(parseRelayAddress(address)).toBe('mac.local:8777');
  });
});
