// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from 'vitest';

import { LanMatch } from '../../src/app/LanMatch.js';
import type { PeerMessage } from '../../src/net/protocol.js';
import type { WebSocketLinkHandlers } from '../../src/platform/WebSocketLink.js';

/**
 * 通信対戦の配線。WebSocket の代わりに、届くメッセージを手で流す接続を差す。
 *
 * 流れそのもの（`LockstepClient`・`LockstepDriver`）は `tests/net/` が見ている。
 * ここで見るのは、ロビーで選んだものが「はじめる」で配られること・始まったら盤面と名札が
 * 出ること・止まったときにどちらの画面で理由を出すか。
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
  closed: () => number;
} {
  const lobby = document.createElement('div');
  const status = document.createElement('p');
  document.body.append(lobby, status);
  const sent: PeerMessage[] = [];
  let closed = 0;
  let relay: WebSocketLinkHandlers | null = null;
  const match = new LanMatch({
    address: 'relay.local:8777',
    keyboard: { anyOf: () => false },
    gamepads: () => [],
    lobby,
    status,
    newSeed: () => 42,
    leave: () => undefined,
    connect: (_url, handlers) => {
      relay = handlers;
      return { send: (message) => sent.push(message), close: () => (closed += 1) };
    },
  });
  if (relay === null) throw new Error('接続を作っていない');
  return { match, lobby, status, sent, relay, closed: () => closed };
}

/** 中継から届いたことにする。 */
function deliver(relay: WebSocketLinkHandlers, message: object): void {
  relay.onMessage(JSON.stringify(message));
}

afterEach(() => document.body.replaceChildren());

describe('通信対戦の配線', () => {
  it('ロビーで選んだものを「はじめる」で配り、始まったら盤面と名札を出す', () => {
    const { match, lobby, sent, relay } = mount();
    match.afterDraw();
    expect(lobby.textContent).toContain('つないでいる');

    deliver(relay, { t: 'welcome', seat: 0, role: 'host', seats: [] });
    match.afterDraw();
    press(lobby, '[data-field="animal-1"] [data-value="mole"]');
    press(lobby, '[data-field="cpu-2"] [data-value="oni"]');
    press(lobby, '[data-action="start"]');

    const start = sent.find((message) => message.t === 'start');
    if (start?.t !== 'start') throw new Error('はじめるの合図を送っていない');
    expect(start.config.match.animals[1]).toBe('mole');
    expect(start.config.cpu[2]).toBe('oni');
    expect(start.config.match.seed).toBe(42);
    expect(match.world).toBeNull();

    // 中継が、その時点の参加者を添えて全員へ配り直す（ホスト本人にも）。
    deliver(relay, { t: 'start', seats: [0], config: start.config });
    expect(match.world).not.toBeNull();
    expect(match.hud?.roster).toEqual([
      { kind: 'human', label: '1P', local: true },
      { kind: 'cpu', level: 'normal' },
      { kind: 'cpu', level: 'oni' },
      { kind: 'cpu', level: 'normal' },
    ]);
    // 人間は自分だけなので、自分の入力がそろえば進められる。
    expect(match.ready).toBe(true);
    match.step();
    expect(match.inProgress).toBe(true);
  });

  it('抜けた人は、CPU に替わった tick から名札も CPU にする', () => {
    const { match, relay, sent } = mount();
    deliver(relay, { t: 'welcome', seat: 0, role: 'host', seats: [1] });
    match.afterDraw();
    const config = { match: { roundLimit: 600, winsToTake: 3, suddenDeath: true, startingHp: [6, 6], seed: 1, animals: ['rabbit', 'fox'] }, cpu: ['easy', 'hard'] };
    deliver(relay, { t: 'start', seats: [0, 1], config });
    expect(match.hud?.roster[1]).toEqual({ kind: 'human', label: '2P', local: false });

    // 2P は1通も送らずに抜けた。次の tick から CPU が受け持つ。
    deliver(relay, { t: 'peer_left', seat: 1, lastTick: -1 });
    expect(match.ready).toBe(true);
    match.step();
    expect(match.hud?.roster[1]).toEqual({ kind: 'cpu', level: 'hard' });
    expect(sent.some((message) => message.t === 'input')).toBe(true);
  });

  it('操作を待っている案内は、待ちが続いたときだけ出す', () => {
    const { match, status, relay } = mount();
    deliver(relay, { t: 'welcome', seat: 0, role: 'host', seats: [1] });
    const config = { match: { roundLimit: 600, winsToTake: 3, suddenDeath: true, startingHp: [6, 6], seed: 1, animals: ['rabbit', 'fox'] }, cpu: ['easy', 'hard'] };
    deliver(relay, { t: 'start', seats: [0, 1], config });
    // 2P の入力は届かないので、先に送ってある分を使い切ると待つ。
    for (let i = 0; i < 100 && match.ready; i += 1) match.step();
    expect(match.ready).toBe(false);

    match.afterDraw();
    expect(status.textContent).toBe('');
    for (let i = 0; i < 40; i += 1) match.afterDraw();
    expect(status.textContent).toContain('2P の操作を待っている');
  });

  it('始まる前に断られたら、ロビーの画面で理由を出す', () => {
    const { match, lobby, relay } = mount();
    relay.onClose(1013);
    match.afterDraw();
    expect(match.world).toBeNull();
    expect(lobby.textContent).toContain('前の試合が続いているか');
  });

  it('始まったあとに切れたら、盤面を残したまま理由を出す', () => {
    const { match, status, relay, sent } = mount();
    deliver(relay, { t: 'welcome', seat: 0, role: 'host', seats: [] });
    match.afterDraw();
    const config = { match: { roundLimit: 600, winsToTake: 3, suddenDeath: true, startingHp: [6, 6, 6, 6], seed: 1, animals: ['rabbit', 'fox', 'frog', 'mole'] }, cpu: ['easy', 'easy', 'easy', 'easy'] };
    deliver(relay, { t: 'start', seats: [0], config });
    relay.onClose(1006);
    match.afterDraw();
    expect(match.world).not.toBeNull();
    expect(match.inProgress).toBe(false);
    expect(status.textContent).toContain('中継との接続が切れた');
    expect(sent.length).toBeGreaterThan(0);
  });

  it('抜けるときは接続を閉じる', () => {
    const { match, closed } = mount();
    match.close();
    expect(closed()).toBe(1);
  });
});
