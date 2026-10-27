import { afterEach, describe, expect, it, vi } from 'vitest';

import { REFUSED_CLOSE_CODE } from '../../src/net/protocol.js';
import { WebSocketLink } from '../../src/platform/WebSocketLink.js';

/**
 * ブラウザの WebSocket の代わり。中継からの知らせ（つながった・閉じた）は、テストが手で起こす。
 *
 * `WebSocketLink` が読むのは、`open`・`message`・`close` の知らせと、`readyState` と `WebSocket.OPEN` だけ。
 */
class FakeSocket extends EventTarget {
  static readonly OPEN = 1;
  /** いちばん新しく作られたもの。 */
  static last: FakeSocket | null = null;
  readyState = 0;
  readonly sent: string[] = [];

  constructor(readonly url: string) {
    super();
    FakeSocket.last = this;
  }

  send(text: string): void {
    this.sent.push(text);
  }

  close(): void {
    // 閉じた知らせは、テストが `closeWith` で起こす。
  }

  /** 中継につながった。 */
  open(): void {
    this.readyState = FakeSocket.OPEN;
    this.dispatchEvent(new Event('open'));
  }

  /** 閉じた（`code` は閉じたときの番号）。 */
  closeWith(code: number): void {
    this.readyState = 3;
    this.dispatchEvent(Object.assign(new Event('close'), { code }));
  }
}

/** 中継につなぎ始め、閉じた知らせの受け口と、作られた WebSocket を返す。 */
function connect(): { link: WebSocketLink; socket: FakeSocket; onClose: ReturnType<typeof vi.fn> } {
  vi.stubGlobal('WebSocket', FakeSocket);
  const onClose = vi.fn();
  const link = new WebSocketLink('ws://relay.local:8777/lockstep', { onMessage: () => undefined, onClose });
  const socket = FakeSocket.last;
  if (socket === null) throw new Error('WebSocket を作っていない');
  expect(socket.url).toBe('ws://relay.local:8777/lockstep');
  return { link, socket, onClose };
}

afterEach(() => {
  vi.unstubAllGlobals();
  FakeSocket.last = null;
});

describe('中継との WebSocket が閉じたときの知らせ', () => {
  it('一度もつながらずに閉じたら、つながっていないと添える（中継に届かなかった。LAN の画面に「中継（…）につなげなかった」）', () => {
    const { socket, onClose } = connect();
    socket.closeWith(1006);
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledWith(1006, false);
  });

  it('つながったあとに閉じたら、つながったと添える', () => {
    const { socket, onClose } = connect();
    socket.open();
    socket.closeWith(1006);
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledWith(1006, true);
  });

  it('閉じたときの番号はそのまま渡す（中継に断られたときの番号を、ほかの切れ方と見分けられる）', () => {
    const { socket, onClose } = connect();
    socket.open();
    socket.closeWith(REFUSED_CLOSE_CODE);
    expect(onClose).toHaveBeenCalledWith(REFUSED_CLOSE_CODE, true);
  });
});
