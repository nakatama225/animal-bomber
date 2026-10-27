// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from 'vitest';

import { LanMatch } from '../../src/app/LanMatch.js';
import type { PeerMessage } from '../../src/net/protocol.js';
import { PadChoice } from '../../src/platform/GamepadInput.js';
import type { WebSocketLinkHandlers } from '../../src/platform/WebSocketLink.js';
import { LobbyChoices } from '../../src/presentation/menu/lanSetup.js';

/**
 * 通信対戦の配線。WebSocket の代わりに、メッセージを手で届ける接続を差す。
 *
 * 流れそのもの（`LockstepClient`・`LockstepDriver`）は `tests/net/` が見ている。
 * ここで見るのは、ロビーで選んだものが「はじめる」で配られること・始まったら盤面と名札が
 * 出ること・接続の段階（`stage`。止まったときに LAN の画面に留まるか、タイトルへ戻るか）。
 */

function press(root: ParentNode, selector: string): void {
  const target = root.querySelector(selector);
  if (!(target instanceof HTMLElement)) throw new Error(`${selector} が無い`);
  target.dispatchEvent(new MouseEvent('click', { detail: 1, bubbles: true }));
}

function mount(): {
  match: LanMatch;
  lobby: HTMLElement;
  status: HTMLElement;
  sent: PeerMessage[];
  relay: WebSocketLinkHandlers;
  url: string;
  closed: () => number;
  log: string[];
} {
  const lobby = document.createElement('div');
  const status = document.createElement('p');
  document.body.append(lobby, status);
  const sent: PeerMessage[] = [];
  const log: string[] = [];
  let closed = 0;
  let relay: WebSocketLinkHandlers | null = null;
  let url = '';
  const match = new LanMatch({
    address: 'relay.local:8777',
    keyboard: { anyOf: () => false, buttonAnyOf: () => false },
    pads: new PadChoice(() => []),
    lobby,
    status,
    newSeed: () => 42,
    choices: new LobbyChoices(),
    askDisconnect: () => log.push('disconnect'),
    uiSound: () => log.push('ui'),
    enteredLobby: () => log.push('entered'),
    connect: (to, handlers) => {
      url = to;
      relay = handlers;
      return { send: (message) => sent.push(message), close: () => (closed += 1) };
    },
  });
  if (relay === null) throw new Error('接続を作っていない');
  return { match, lobby, status, sent, relay, url, closed: () => closed, log };
}

/** 中継から届いたことにする。 */
function deliver(relay: WebSocketLinkHandlers, message: object): void {
  relay.onMessage(JSON.stringify(message));
}

afterEach(() => document.body.replaceChildren());

describe('通信対戦の配線', () => {
  it('ロビーで選んだものを「はじめる」で配り、始まったら盤面と名札を出す', () => {
    const { match, lobby, sent, relay, url, log } = mount();
    expect(url).toBe('ws://relay.local:8777/lockstep');
    // つないでいる最中は、ロビーを写さない（LAN の画面に「接続しています…」を出すのは MenuView）。
    match.afterDraw();
    expect(match.stage).toEqual({ kind: 'connecting' });
    expect(lobby.childElementCount).toBe(0);
    expect(log).toEqual([]);

    deliver(relay, { t: 'welcome', seat: 0, role: 'host', seats: [] });
    match.afterDraw();
    expect(match.stage).toEqual({ kind: 'lobby' });
    expect(lobby.querySelector('[data-screen="lobby"]')).not.toBeNull();
    // 初めてロビーを写したときに知らせる（確認の画面を畳むため）。2回目からは知らせない。
    expect(log).toEqual(['entered']);
    match.afterDraw();
    expect(log).toEqual(['entered']);
    press(lobby, '[data-field="animal-1"] [data-value="mole"]');
    press(lobby, '[data-field="cpu-2"] [data-value="oni"]');
    press(lobby, '[data-action="start"]');

    const start = sent.find((message) => message.t === 'start');
    if (start?.t !== 'start') throw new Error('はじめるの合図を送っていない');
    expect(start.config.match.animals[1]).toBe('mole');
    expect(start.config.cpu[2]).toBe('oni');
    expect(start.config.match.seed).toBe(42);
    expect(match.world).toBeNull();

    // 中継が、その時点の参加者を添えて全員へ配り直す（ホスト自身にも）。
    deliver(relay, { t: 'start', seats: [0], config: start.config, match: 1 });
    expect(match.world).not.toBeNull();
    expect(match.hud?.roster).toEqual([
      { kind: 'human', label: '1P', local: true },
      { kind: 'cpu', number: 1, level: 'normal' },
      { kind: 'cpu', number: 2, level: 'oni' },
      { kind: 'cpu', number: 3, level: 'normal' },
    ]);
    // 人間は自分だけなので、自分の入力がそろえば進められる。
    expect(match.ready).toBe(true);
    match.step();
    expect(match.inProgress).toBe(true);
    expect(match.stage).toEqual({ kind: 'playing' });
  });

  it('ホストがロビーで選んだものは、始まる前にゲストの画面へ届く', () => {
    const host = mount();
    // 先にゲストが居る部屋に入ったホストは、選び直す前の設定もすぐ配る。
    deliver(host.relay, { t: 'welcome', seat: 0, role: 'host', seats: [1] });
    const first = host.sent.find((message) => message.t === 'settings');
    expect(first?.t === 'settings' ? first.config.match.animals : undefined).toEqual(['rabbit', 'frog', 'fox', 'elephant']);
    host.match.afterDraw();
    press(host.lobby, '[data-field="animal-1"] [data-value="mole"]');
    press(host.lobby, '[data-field="wins"] [data-value="7"]');
    const shared = host.sent.filter((message) => message.t === 'settings');
    const last = shared.at(-1);
    if (last?.t !== 'settings') throw new Error('設定を配っていない');
    expect(last.config.match.animals[1]).toBe('mole');
    expect(last.config.match.winsToTake).toBe(7);

    document.body.replaceChildren();
    // 中継が転送した同じ1通を、ゲストが受け取る。
    const guest = mount();
    deliver(guest.relay, { t: 'welcome', seat: 1, role: 'guest', seats: [0] });
    deliver(guest.relay, JSON.parse(JSON.stringify(last)));
    guest.match.afterDraw();
    expect(guest.lobby.querySelector('[data-shared-slot="1"]')?.textContent).toContain('もぐら');
    expect(guest.lobby.querySelector('[data-shared-rules]')?.textContent).toContain('7勝先取');
  });

  it('抜けたプレイヤーは、CPU に替わった tick から名札も CPU にする（札は CPU1、入れ替わりの通知の呼び方は元の番号）', () => {
    const { match, relay, sent } = mount();
    deliver(relay, { t: 'welcome', seat: 0, role: 'host', seats: [1] });
    match.afterDraw();
    const config = { match: { roundLimit: 600, winsToTake: 3, suddenDeath: true, startingHp: [6, 6], seed: 1, animals: ['rabbit', 'fox'] }, cpu: ['easy', 'hard'] };
    deliver(relay, { t: 'start', seats: [0, 1], config, match: 1 });
    expect(match.hud?.roster[1]).toEqual({ kind: 'human', label: '2P', local: false });

    // 2P は1通も送らずに抜けた。次の tick から CPU が受け持つ。
    deliver(relay, { t: 'peer_left', seat: 1, lastTick: -1 });
    // 知らせが届いただけでは、まだ人間の名札のまま（替わるのは次の tick から）。
    expect(match.hud?.roster[1]).toEqual({ kind: 'human', label: '2P', local: false });
    expect(match.ready).toBe(true);
    match.step();
    expect(match.hud?.roster[1]).toEqual({ kind: 'cpu', number: 1, level: 'hard', label: '2P' });
    expect(sent.some((message) => message.t === 'input')).toBe(true);
  });

  it('操作を待っている案内は、待ちが続いたときだけ出す', () => {
    const { match, status, relay } = mount();
    deliver(relay, { t: 'welcome', seat: 0, role: 'host', seats: [1] });
    const config = { match: { roundLimit: 600, winsToTake: 3, suddenDeath: true, startingHp: [6, 6], seed: 1, animals: ['rabbit', 'fox'] }, cpu: ['easy', 'hard'] };
    deliver(relay, { t: 'start', seats: [0, 1], config, match: 1 });
    // 2P の入力は届かないので、先に送ってある分を使い切ると待つ。
    for (let i = 0; i < 100 && match.ready; i += 1) match.step();
    expect(match.ready).toBe(false);

    match.afterDraw();
    expect(status.textContent).toBe('');
    // 案内の帯は盤面の下の端に重なるので、出す文が無い間は隠す。
    expect(status.hidden).toBe(true);
    for (let i = 0; i < 40; i += 1) match.afterDraw();
    expect(status.textContent).toContain('2P の操作を待っている');
    expect(status.hidden).toBe(false);
  });

  it('抜けるときは、案内の帯を空にして隠す（1台の試合の盤面に、前の案内を残さない）', () => {
    const { match, status, relay } = mount();
    deliver(relay, { t: 'welcome', seat: 0, role: 'host', seats: [1] });
    const config = { match: { roundLimit: 600, winsToTake: 3, suddenDeath: true, startingHp: [6, 6], seed: 1, animals: ['rabbit', 'fox'] }, cpu: ['easy', 'hard'] };
    deliver(relay, { t: 'start', seats: [0, 1], config, match: 1 });
    // 2P の入力が届かないので、先に送ってある分を使い切ると待ち、待ちが続くと帯に出す。
    for (let i = 0; i < 100 && match.ready; i += 1) match.step();
    for (let i = 0; i < 40; i += 1) match.afterDraw();
    expect(status.hidden).toBe(false);
    match.close();
    expect(status.textContent).toBe('');
    expect(status.hidden).toBe(true);
  });

  it('始まる前に断られたら、LAN の画面に留まって理由を出す段階になる（ロビーは写さない）', () => {
    const { match, lobby, status, relay } = mount();
    relay.onClose(1013, true);
    match.afterDraw();
    expect(match.world).toBeNull();
    expect(match.stage).toEqual({ kind: 'cannotJoin', reason: '前の試合が続いているか、定員いっぱいで入れなかった' });
    expect(lobby.childElementCount).toBe(0);
    // 帯にも出さない（LAN の画面が出す）。
    expect(status.textContent).toBe('');
  });

  it('中継に一度もつながらずに閉じたら、中継の場所を添えて「つなげなかった」と出す。つながったあとに閉じたら「切れた」', () => {
    const never = mount();
    never.relay.onClose(1006, false);
    expect(never.match.stage).toEqual({ kind: 'cannotJoin', reason: '中継（relay.local:8777）につなげなかった' });

    document.body.replaceChildren();
    const opened = mount();
    opened.relay.onClose(1006, true);
    expect(opened.match.stage).toEqual({ kind: 'cannotJoin', reason: '中継との接続が切れた' });
  });

  it('ロビーへ移ったあとに切れたら、試合の前でも最中でも「サーバとの接続が切れました」でタイトルへ戻す段階になる（原型の onclose）', () => {
    const inLobby = mount();
    deliver(inLobby.relay, { t: 'welcome', seat: 1, role: 'guest', seats: [0] });
    inLobby.relay.onClose(1006, true);
    expect(inLobby.match.stage).toEqual({ kind: 'lost', notice: 'サーバとの接続が切れました' });
    // ロビーの画面を写し直さない（タイトルへ戻すのは Shell）。
    inLobby.match.afterDraw();
    expect(inLobby.lobby.childElementCount).toBe(0);

    document.body.replaceChildren();
    const { match, relay } = mount();
    deliver(relay, { t: 'welcome', seat: 0, role: 'host', seats: [] });
    match.afterDraw();
    const config = { match: { roundLimit: 600, winsToTake: 3, suddenDeath: true, startingHp: [6, 6, 6, 6], seed: 1, animals: ['rabbit', 'fox', 'frog', 'mole'] }, cpu: ['easy', 'easy', 'easy', 'easy'] };
    deliver(relay, { t: 'start', seats: [0], config, match: 1 });
    // 始めたときにいなかった枠は、前から CPU1・CPU2・CPU3（原型の setupPlayersLan の cpuIdx）。
    expect(match.hud?.roster.map((c) => (c.kind === 'cpu' ? `CPU${c.number}` : c.label))).toEqual(['1P', 'CPU1', 'CPU2', 'CPU3']);
    relay.onClose(1006, true);
    expect(match.inProgress).toBe(false);
    expect(match.stage).toEqual({ kind: 'lost', notice: 'サーバとの接続が切れました' });
  });

  it('ロビーでホストが抜けたら、ゲストは「ホストとの接続が切れました」でタイトルへ戻す段階になる。ほかの端末が抜けても戻さない', () => {
    const { match, relay, lobby } = mount();
    deliver(relay, { t: 'welcome', seat: 1, role: 'guest', seats: [0, 2] });
    match.afterDraw();
    deliver(relay, { t: 'peer_left', seat: 2, lastTick: -1 });
    expect(match.stage).toEqual({ kind: 'lobby' });
    deliver(relay, { t: 'peer_left', seat: 0, lastTick: -1 });
    expect(match.stage).toEqual({ kind: 'lost', notice: 'ホストとの接続が切れました' });
    // 抜けたあとの様子でロビーを写し直さない。
    const before = lobby.innerHTML;
    match.afterDraw();
    expect(lobby.innerHTML).toBe(before);
  });

  it('ホストより先に入ったゲストは、ホストがまだいなくても戻さない（ホストを見てからいなくなったときだけ）', () => {
    const { match, relay } = mount();
    deliver(relay, { t: 'welcome', seat: 1, role: 'guest', seats: [] });
    expect(match.stage).toEqual({ kind: 'lobby' });
    deliver(relay, { t: 'peer_joined', seat: 0 });
    expect(match.stage).toEqual({ kind: 'lobby' });
    deliver(relay, { t: 'peer_left', seat: 0, lastTick: -1 });
    expect(match.stage).toEqual({ kind: 'lost', notice: 'ホストとの接続が切れました' });
  });

  it('抜けるときは接続を閉じる', () => {
    const { match, closed } = mount();
    match.close();
    expect(closed()).toBe(1);
  });
});
