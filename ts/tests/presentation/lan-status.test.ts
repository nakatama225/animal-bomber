import { describe, expect, it } from 'vitest';

import { IDLE_INPUT } from '../../src/domain/input/PlayerInput.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import { OUT } from '../../src/domain/state/Life.js';
import { LockstepClient } from '../../src/net/LockstepClient.js';
import type { LanSettings } from '../../src/net/protocol.js';
import { describeLanPhase } from '../../src/presentation/hud/lanStatus.js';
import { hooksWith } from '../net/fakeRelay.js';

const SETTINGS: LanSettings = {
  match: defaultMatchConfig(3, ['rabbit', 'elephant', 'fox', 'frog']),
  cpu: ['normal', 'normal', 'normal', 'normal'],
};

function client(): LockstepClient {
  return new LockstepClient({ send: () => undefined }, hooksWith(() => IDLE_INPUT));
}

const text = (message: object): string => JSON.stringify(message);

describe('通信対戦の案内', () => {
  it('始まる前は出さない（ロビーの画面が出す）', () => {
    const c = client();
    expect(describeLanPhase(c.phase)).toBe('');
    c.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    expect(describeLanPhase(c.phase)).toBe('');
  });

  it('試合中は、操作を待っているプレイヤーがいるときだけ出す', () => {
    const c = client();
    c.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    c.receive(text({ t: 'start', seats: [0, 1], config: SETTINGS, match: 1 }));

    // 最初の 3 tick ぶんは自分の入力しか無いので、2P を待っている。
    expect(describeLanPhase(c.phase)).toBe('2P の操作を待っている');
    c.receive(text({ t: 'input', seat: 1, tick: 0, bits: 0, match: 1 }));
    expect(describeLanPhase(c.phase)).toBe('');
  });

  it('ずれたとき・止めたときは、全員がタイトルへ戻ってからつなぎ直すよう出す（Python 版の lan_status.py の文）', () => {
    // 自分だけつなぎ直しても、ほかの端末がつながっている間は中継に断られる。
    const c = client();
    c.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    c.receive(text({ t: 'start', seats: [0, 1], config: SETTINGS, match: 1 }));
    c.receive(text({ t: 'desync', tick: 19, reports: [] }));
    expect(describeLanPhase(c.phase)).toBe(
      '端末どうしで試合がずれたので止めた（tick 19）。もう一度遊ぶときは、全員が「設定へ」でタイトルへ戻ってから、つなぎ直す',
    );

    const lost = client();
    lost.disconnected();
    expect(describeLanPhase(lost.phase)).toBe(
      '中継との接続が切れた。もう一度遊ぶときは、全員が「設定へ」でタイトルへ戻ってから、つなぎ直す',
    );

    const refused = client();
    refused.disconnected('前の試合が続いているか、定員いっぱいで入れなかった');
    expect(describeLanPhase(refused.phase)).toMatch(/^前の試合が続いているか/);
  });

  it('試合が終わったら、次の試合の始め方を出す。始められるのはホストだけ', () => {
    const finishedAs = (seat: 0 | 1): string => {
      const c = client();
      c.receive(text({ t: 'welcome', seat, role: seat === 0 ? 'host' : 'guest', seats: seat === 0 ? [] : [0] }));
      const config = { ...SETTINGS, match: { ...SETTINGS.match, winsToTake: 1 } };
      c.receive(text({ t: 'start', seats: [0, 1], config, match: 1 }));
      if (c.phase.kind !== 'playing') throw new Error('始まっていない');
      c.receive(text({ t: 'input', seat: 1 - seat, tick: 0, bits: 0, match: 1 }));
      const loser = seat === 0 ? [1, 2, 3] : [0, 2, 3];
      for (const id of loser) c.phase.session.world.players[id]!.life = OUT;
      c.step();
      expect(c.phase.session.match.finished).toBe(true);
      // 次の tick の相手の入力が届いていて、待ちの案内が出ない状態で見る。
      c.receive(text({ t: 'input', seat: 1 - seat, tick: 1, bits: 0, match: 1 }));
      return describeLanPhase(c.phase);
    };
    expect(finishedAs(0)).toBe('試合が終わった。「もういっかい」で、同じ顔ぶれ・同じ設定のまま次の試合を始める');
    expect(finishedAs(1)).toBe('試合が終わった。1P（ホスト）が「もういっかい」を押すと、次の試合が始まる');
  });

  it('ホストが抜けたあとに試合が終わったら、ゲストには次の試合が始められないことを出す', () => {
    // 次の試合を始められるのはホストだけ。来ないホストを待つよう案内しない。
    const c = client();
    c.receive(text({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    const config = { ...SETTINGS, match: { ...SETTINGS.match, winsToTake: 1 } };
    c.receive(text({ t: 'start', seats: [0, 1], config, match: 1 }));
    if (c.phase.kind !== 'playing') throw new Error('始まっていない');
    // ホストは tick 0 の入力を最後に抜けた。知らせが届いた時点で、案内を替える（CPU に替わる tick を待たない）。
    c.receive(text({ t: 'input', seat: 0, tick: 0, bits: 0, match: 1 }));
    c.receive(text({ t: 'peer_left', seat: 0, lastTick: 0 }));
    for (const id of [0, 2, 3]) c.phase.session.world.players[id]!.life = OUT;
    c.step();
    expect(c.phase.session.match.finished).toBe(true);
    expect(describeLanPhase(c.phase)).toBe(
      '試合が終わった。1P（ホスト）が抜けたので、次の試合は始められない。もう一度遊ぶときは、全員が「設定へ」でタイトルへ戻ってから、つなぎ直す',
    );
  });
});
