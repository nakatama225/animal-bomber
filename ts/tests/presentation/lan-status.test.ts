import { describe, expect, it } from 'vitest';

import { IDLE_INTENT } from '../../src/domain/intent/PlayerIntent.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import { OUT } from '../../src/domain/state/Life.js';
import { LockstepClient } from '../../src/net/LockstepClient.js';
import type { LanSettings } from '../../src/net/protocol.js';
import { describeLanPhase } from '../../src/presentation/hud/lanStatus.js';
import { hooksWith } from '../net/fakeRelay.js';

const SETTINGS: LanSettings = {
  match: defaultMatchConfig(3, ['rabbit', 'elephant', 'fox', 'frog']),
  cpu: 'normal',
};

function client(): LockstepClient {
  return new LockstepClient({ send: () => undefined }, hooksWith(() => IDLE_INTENT));
}

const text = (message: object): string => JSON.stringify(message);

describe('通信対戦の案内', () => {
  it('つないでいる間', () => {
    expect(describeLanPhase(client().phase)).toBe('中継サーバにつないでいる…');
  });

  it('待っている間は、自分の番号とつながっている人を出し、ホストには始め方を出す', () => {
    const host = client();
    host.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    host.receive(text({ t: 'peer_joined', seat: 2 }));
    const guest = client();
    guest.receive(text({ t: 'welcome', seat: 2, role: 'guest', seats: [0] }));

    expect(describeLanPhase(host.phase)).toBe(
      'あなたは 1P。つながっている人：1P・3P。全員そろったら「はじめる」を押す',
    );
    expect(describeLanPhase(guest.phase)).toBe(
      'あなたは 3P。つながっている人：1P・3P。1P が始めるのを待っている',
    );
  });

  it('試合中は、操作を待っている人がいるときだけ出す', () => {
    const c = client();
    c.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    c.receive(text({ t: 'start', seats: [0, 1], config: SETTINGS }));

    // 最初の 3 tick ぶんは自分の入力しか無いので、2P を待っている。
    expect(describeLanPhase(c.phase)).toBe('2P の操作を待っている');
    c.receive(text({ t: 'input', seat: 1, tick: 0, bits: 0 }));
    expect(describeLanPhase(c.phase)).toBe('');
  });

  it('ずれたとき・止めたときは、全員が閉じてから開き直すよう出す', () => {
    // 読み込み直すだけでは、ほかの人がつながっている間は中継に断られる。
    const c = client();
    c.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    c.receive(text({ t: 'start', seats: [0, 1], config: SETTINGS }));
    c.receive(text({ t: 'desync', tick: 19, reports: [] }));
    expect(describeLanPhase(c.phase)).toBe(
      '端末どうしで試合がずれたので止めた（tick 19）。もう一度遊ぶときは、全員がページを閉じてから開き直す',
    );

    const lost = client();
    lost.disconnected();
    expect(describeLanPhase(lost.phase)).toBe(
      '中継との接続が切れた。もう一度遊ぶときは、全員がページを閉じてから開き直す',
    );

    const refused = client();
    refused.disconnected('前の試合が続いているか、定員いっぱいで入れなかった');
    expect(describeLanPhase(refused.phase)).toMatch(/^前の試合が続いているか/);
  });

  it('試合が終わったら、次の試合の始め方を出す', () => {
    const c = client();
    c.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    c.receive(text({ t: 'start', seats: [0], config: { ...SETTINGS, match: { ...SETTINGS.match, winsToTake: 1 } } }));
    if (c.phase.kind !== 'playing') throw new Error('始まっていない');
    for (const id of [1, 2, 3]) c.phase.session.world.players[id]!.life = OUT;
    c.step();

    expect(c.phase.session.match.finished).toBe(true);
    expect(describeLanPhase(c.phase)).toBe('試合が終わった。もう一度遊ぶときは、全員がページを閉じてから開き直す');
  });
});
