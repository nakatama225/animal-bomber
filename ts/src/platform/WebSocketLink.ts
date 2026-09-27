import { encodePeerMessage, LOCKSTEP_PATH, type PeerLink, type PeerMessage } from '../net/protocol.js';

export interface WebSocketLinkHandlers {
  /** 中継から文字列が届いた。 */
  readonly onMessage: (text: string) => void;
  /**
   * 接続が切れた（つなげなかった場合も含む）。
   *
   * @param code 閉じたときの番号。中継に断られたときは `REFUSED_CLOSE_CODE`
   */
  readonly onClose: (code: number) => void;
}

/**
 * 中継サーバとの WebSocket。ブラウザの API に触れるので、この層に置く。
 *
 * 通信の層（`net/`）は、送る口（`PeerLink`）と、届いた文字列を受け取る関数しか知らない。
 * WebSocket をここに閉じ込めておくと、`net/` は node のテストでそのまま動く。
 */
export class WebSocketLink implements PeerLink {
  readonly #socket: WebSocket;

  constructor(url: string, handlers: WebSocketLinkHandlers) {
    this.#socket = new WebSocket(url);
    this.#socket.addEventListener('message', (event: MessageEvent<unknown>) => {
      if (typeof event.data === 'string') handlers.onMessage(event.data);
    });
    this.#socket.addEventListener('close', (event: CloseEvent) => handlers.onClose(event.code));
  }

  /**
   * 送る。つながる前と切れたあとは捨てる。
   *
   * 最初に送るのは `welcome` を受け取ったあとなので、つながる前に送ることはない。
   * 切れたあとは `onClose` から試合を止めるので、捨ててよい。
   */
  readonly send = (message: PeerMessage): void => {
    if (this.#socket.readyState === WebSocket.OPEN) this.#socket.send(encodePeerMessage(message));
  };
}

/**
 * 中継サーバの場所から、ロックステップの中継につなぐ URL を作る。
 *
 * @param address `parseRelayAddress` で確かめた「ホスト名:ポート」
 */
export function lockstepUrl(address: string): string {
  return `ws://${address}${LOCKSTEP_PATH}`;
}

/**
 * URL の `?relay=` に書かれた値から、中継サーバの「ホスト名:ポート」を取り出す。
 *
 * `http://` を付けて貼られても、ホスト名とポートだけを使う。
 * ⚠️ 値をそのまま URL に埋めない。末尾に `/` が付いているだけでパスが `//lockstep` になり、
 * 原型の中継の部屋に入ってしまう。空白が混ざると WebSocket を作る時点で例外になる。
 *
 * @returns 読めなければ null（ポートが無い場合も含む）
 */
export function parseRelayAddress(value: string): string | null {
  const text = value.trim();
  const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(text) ? text : `ws://${text}`;
  let url: URL;
  try {
    url = new URL(withScheme);
  } catch {
    return null;
  }
  const onlyHost = (url.pathname === '/' || url.pathname === '') && url.search === '' && url.hash === '';
  if (!onlyHost || url.hostname === '' || url.port === '' || url.username !== '' || url.password !== '') {
    return null;
  }
  return url.host;
}
