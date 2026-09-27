import { describe, expect, it } from 'vitest';

import { IDLE_INTENT } from '../../src/domain/intent/PlayerIntent.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import { LockstepClient } from '../../src/net/LockstepClient.js';
import type { LanSettings, PeerMessage } from '../../src/net/protocol.js';
import { hooksWith } from './fakeRelay.js';

const SETTINGS: LanSettings = {
  match: defaultMatchConfig(7, ['rabbit', 'elephant', 'fox', 'frog']),
  cpu: 'easy',
};

function client(): { client: LockstepClient; sent: PeerMessage[] } {
  const sent: PeerMessage[] = [];
  const c = new LockstepClient({ send: (m) => sent.push(m) }, hooksWith(() => IDLE_INTENT));
  return { client: c, sent };
}

const text = (message: object): string => JSON.stringify(message);

describe('つないでから始まるまで', () => {
  it('welcome で自分の番号を受け取り、先に居た人と合わせて一覧にする', () => {
    const { client: c } = client();
    expect(c.phase.kind).toBe('connecting');

    c.receive(text({ t: 'welcome', seat: 2, role: 'guest', seats: [1, 0] }));

    expect(c.phase).toEqual({ kind: 'lobby', seat: 2, present: [0, 1, 2] });
  });

  it('待っている間に入った人・抜けた人を一覧に反映する', () => {
    const { client: c } = client();
    c.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    c.receive(text({ t: 'peer_joined', seat: 3 }));
    c.receive(text({ t: 'peer_joined', seat: 1 }));
    c.receive(text({ t: 'peer_left', seat: 3, lastTick: -1 }));

    expect(c.phase).toEqual({ kind: 'lobby', seat: 0, present: [0, 1] });
  });

  it('始める合図を送れるのは、待っている間のホストだけ', () => {
    const host = client();
    const guest = client();
    expect(host.client.requestStart(SETTINGS)).toBe(false); // まだ番号を受け取っていない
    host.client.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    guest.client.receive(text({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));

    expect(guest.client.requestStart(SETTINGS)).toBe(false);
    expect(host.client.requestStart(SETTINGS)).toBe(true);
    expect(host.sent).toEqual([{ t: 'start', config: SETTINGS }]);
  });

  it('合図を送っただけでは始めず、中継から届いた start で始める', () => {
    // ホストだけ先に始めると、人間の一覧の食い違いに気づく場所がなくなる。
    const { client: c, sent } = client();
    c.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    c.requestStart(SETTINGS);
    expect(c.phase.kind).toBe('lobby');

    c.receive(text({ t: 'start', seats: [0, 1], config: SETTINGS }));

    expect(c.phase.kind).toBe('playing');
    // 始めた時点で、最初の 3 tick ぶんの何もしない意思を送っている。
    expect(sent.filter((m) => m.t === 'input').map((m) => m.t === 'input' && m.tick)).toEqual([0, 1, 2]);
  });

  it('待つのは人間の枠だけ', () => {
    const { client: c } = client();
    c.receive(text({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    c.receive(text({ t: 'start', seats: [0, 1], config: SETTINGS }));
    if (c.phase.kind !== 'playing') throw new Error('始まっていない');

    // 待つのは人間の枠（ホストの0番）だけ。CPU の2番・3番は待たない。
    expect(c.phase.driver.waitingFor()).toEqual([0]);
    for (let t = 0; t < 3; t += 1) c.receive(text({ t: 'input', seat: 0, tick: t, bits: 0 }));
    for (let i = 0; i < 3; i += 1) expect(c.step()).not.toBeNull();
    expect(c.phase.driver.waitingFor()).toEqual([0]);
  });
});

describe('止めるとき', () => {
  it('始まった試合の参加者に自分がいなければ止める', () => {
    const { client: c } = client();
    c.receive(text({ t: 'welcome', seat: 2, role: 'guest', seats: [0, 1] }));

    c.receive(text({ t: 'start', seats: [0, 1], config: SETTINGS }));

    expect(c.phase.kind).toBe('failed');
  });

  it('動物の数より多い人数で始まったら止める', () => {
    const { client: c } = client();
    c.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    const twoAnimals = { ...SETTINGS, match: { ...SETTINGS.match, animals: ['rabbit', 'fox'] } };

    c.receive(text({ t: 'start', seats: [0, 1, 2], config: twoAnimals }));

    expect(c.phase).toMatchObject({ kind: 'failed', reason: expect.stringContaining('プレイヤー 2') });
  });

  it('約束に合わないメッセージが届いたら止め、そのあとは何も受け取らない', () => {
    const { client: c } = client();
    c.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [] }));

    c.receive(text({ t: 'peer_joined', seat: 9 }));
    c.receive(text({ t: 'peer_joined', seat: 1 }));

    expect(c.phase).toMatchObject({ kind: 'failed', reason: expect.stringContaining('約束に合わない') });
  });

  it('試合中に入力の順が乱れても、例外を外へ出さずに止める', () => {
    const { client: c } = client();
    c.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    c.receive(text({ t: 'start', seats: [0, 1], config: SETTINGS }));

    c.receive(text({ t: 'input', seat: 1, tick: 5, bits: 0 }));

    expect(c.phase).toMatchObject({ kind: 'failed', reason: expect.stringContaining('順が乱れた') });
    // 原因を調べられるように、元の例外も残す。
    expect(c.phase.kind === 'failed' && c.phase.cause).toBeInstanceOf(Error);
    expect(c.step()).toBeNull();
  });

  it('中継との接続が切れたら止める', () => {
    const { client: c } = client();
    c.disconnected();
    expect(c.phase.kind).toBe('failed');
  });
});
