import { encodePeerMessage, LOCKSTEP_PATH, type PeerLink, type PeerMessage } from '../net/protocol.js';

export interface WebSocketLinkHandlers {
  /** 中継から文字列が届いた。 */
  readonly onMessage: (text: string) => void;
  /**
   * 接続が切れた（つなげなかった場合も含む）。
   *
   * @param code 閉じたときの番号。中継に断られたときは `REFUSED_CLOSE_CODE`
   * @param opened 一度でもつながったか。false なら、中継に届かなかった（中継が立っていない・名前が違う、など）
   */
  readonly onClose: (code: number, opened: boolean) => void;
}

/**
 * 中継サーバとの WebSocket。ブラウザの API に触れるので、この層に置く。
 *
 * 通信の層（`net/`）は、送る口（`PeerLink`）と、届いた文字列を受け取る関数しか知らない。
 * WebSocket をここに閉じ込めておくと、`net/` は node のテストでそのまま動く。
 */
export class WebSocketLink implements PeerLink {
  readonly #socket: WebSocket;
  /** 一度でもつながったか（`open` が届いたか）。 */
  #opened = false;

  constructor(url: string, handlers: WebSocketLinkHandlers) {
    this.#socket = new WebSocket(url);
    this.#socket.addEventListener('open', () => {
      this.#opened = true;
    });
    this.#socket.addEventListener('message', (event: MessageEvent<unknown>) => {
      if (typeof event.data === 'string') handlers.onMessage(event.data);
    });
    this.#socket.addEventListener('close', (event: CloseEvent) => handlers.onClose(event.code, this.#opened));
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

  /** 閉じる。中継は、この端末が抜けたものとして扱う。 */
  close(): void {
    this.#socket.close(1000, 'left');
  }
}

/**
 * 中継サーバの場所から、ロックステップの中継につなぐ URL を作る。
 *
 * @param address `parseRelayAddress` で検証した「ホスト名:ポート」
 */
export function lockstepUrl(address: string): string {
  return `ws://${address}${LOCKSTEP_PATH}`;
}

/** 中継サーバの既定のポート。`server/` の `DEFAULT_PORT` と同じ値。 */
const DEFAULT_RELAY_PORT = 8777;

/**
 * LAN の画面の「たてる」「さんかする」と、値を省いた `?relay` でつなぐ中継の「ホスト名:ポート」。このページを配っている
 * 端末の中継を指す（原型も、開いたページのアドレスにつなぐ。L3727-3731）。
 *
 * - 中継が `/ts/` の下で配ったページ：ページと同じポート。中継は `--port` で別のポートに立てられ、
 *   そのときはページもそのポートから届く。8777 番に決め打ちすると、そこにいない中継（または別の中継）へ
 *   つなぎにいく
 * - それ以外（開発サーバから開いたページなど）：8777 番（中継の既定のポート）
 * - ポートの無い URL（80 番）で配られたページも 8777 番。中継を 80 番で立てることは想定しない。
 *   `ws://…:80` は既定のポートとして省かれ、`parseRelayAddress` が「ポートが無い」として受け付けない
 *
 * @param location いまのページの場所（`window.location` の一部。テストで差し替えられるよう受け取る）
 */
export function defaultRelayAddress(location: {
  readonly pathname: string;
  readonly hostname: string;
  readonly port: string;
}): string {
  const servedByRelay = location.pathname.startsWith('/ts/') && location.port !== '';
  return `${location.hostname}:${servedByRelay ? location.port : DEFAULT_RELAY_PORT}`;
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
