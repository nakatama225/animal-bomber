import { describe, expect, it } from 'vitest';

import { GameSession } from '../../src/app/GameSession.js';
import { IDLE_INPUT } from '../../src/domain/input/PlayerInput.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import { LockstepClient, type LanHooks } from '../../src/net/LockstepClient.js';
import type { LanSettings, PeerMessage } from '../../src/net/protocol.js';
import { hooksWith } from './fakeRelay.js';

const SETTINGS: LanSettings = {
  match: defaultMatchConfig(7, ['rabbit', 'elephant', 'fox', 'frog']),
  cpu: ['easy', 'easy', 'easy', 'easy'],
};

function client(): { client: LockstepClient; sent: PeerMessage[] } {
  const sent: PeerMessage[] = [];
  const c = new LockstepClient({ send: (m) => sent.push(m) }, hooksWith(() => IDLE_INPUT));
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

  it('試合の前に始める合図を送れるのは、ホストだけ（番号を受け取る前は送らない）', () => {
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

    c.receive(text({ t: 'start', seats: [0, 1], config: SETTINGS, match: 1 }));

    expect(c.phase.kind).toBe('playing');
    // 始めた時点で、tick 0〜2 の3通を送っている（中身は始まった時点で押している内容。この試合の窓口は何も押さない）。
    expect(sent.filter((m) => m.t === 'input').map((m) => m.t === 'input' && m.tick)).toEqual([0, 1, 2]);
  });

  it('待つのは人間の枠だけ', () => {
    const { client: c } = client();
    c.receive(text({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    c.receive(text({ t: 'start', seats: [0, 1], config: SETTINGS, match: 1 }));
    if (c.phase.kind !== 'playing') throw new Error('始まっていない');

    // 待つのは人間の枠（ホストの0番）だけ。CPU の2番・3番は待たない。
    expect(c.phase.driver.waitingFor()).toEqual([0]);
    for (let t = 0; t < 3; t += 1) c.receive(text({ t: 'input', seat: 0, tick: t, bits: 0, match: 1 }));
    for (let i = 0; i < 3; i += 1) expect(c.step()).not.toBeNull();
    expect(c.phase.driver.waitingFor()).toEqual([0]);
  });
});

describe('始まる前の設定', () => {
  /** SETTINGS と、動物・種・CPU の強さが違う設定。 */
  const OTHER: LanSettings = {
    match: defaultMatchConfig(99, ['mole', 'frog', 'rabbit', 'elephant']),
    cpu: ['oni', 'oni', 'oni', 'oni'],
  };

  it('ホストは、選んでいる設定をつながったときと選び直すたびに配り、人が入ってきたら配り直す', () => {
    // 中継は設定を覚えない。あとから入った人には、ホストが配り直した分が届く。
    const { client: c, sent } = client();
    const shared = (): PeerMessage[] => sent.filter((m) => m.t === 'settings');
    // 番号を受け取る前は、ホストかどうかが分からないので送らない。
    c.shareSettings(SETTINGS);
    expect(shared()).toEqual([]);
    // 先にゲストが居る部屋にホストが入ることがある（サーバの Mac のブラウザは、あとから開いても 0 番）。
    c.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [1] }));
    expect(shared()).toEqual([{ t: 'settings', config: SETTINGS }]);
    c.shareSettings(OTHER);
    c.receive(text({ t: 'peer_joined', seat: 2 }));
    expect(shared()).toEqual([
      { t: 'settings', config: SETTINGS },
      { t: 'settings', config: OTHER },
      { t: 'settings', config: OTHER },
    ]);
  });

  it('ゲストは設定を配らず、届いたホストの設定を、待っている間の段階に持つ', () => {
    const { client: c, sent } = client();
    c.receive(text({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    c.shareSettings(SETTINGS);
    expect(sent).toEqual([]);

    c.receive(text({ t: 'settings', config: OTHER }));

    expect(c.phase).toEqual({ kind: 'lobby', seat: 1, present: [0, 1], hostSettings: OTHER });
  });

  it('試合は start の設定だけから作る。始まる前に届いた設定は使わない', () => {
    // 始まる前の設定は画面に出すためのもの。ホストは「はじめる」を押した時点の設定を start で配り直し、
    // 全員がその1通から試合を作る。前に届いた設定を使うと、選び直しと入れ違った端末だけ別の試合になる。
    const { client: c } = client();
    c.receive(text({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    c.receive(text({ t: 'settings', config: OTHER }));
    c.receive(text({ t: 'start', seats: [0, 1], config: SETTINGS, match: 1 }));

    if (c.phase.kind !== 'playing') throw new Error('始まっていない');
    expect(c.phase.settings).toEqual(SETTINGS);
    expect(c.phase.session.world.players.map((p) => p.animal)).toEqual(SETTINGS.match.animals);
  });

  it('始まったあとは、ホストも設定を配らない', () => {
    const { client: c, sent } = client();
    c.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    c.receive(text({ t: 'start', seats: [0], config: SETTINGS, match: 1 }));
    const before = sent.length;
    c.shareSettings(OTHER);
    expect(sent.slice(before).filter((m) => m.t === 'settings')).toEqual([]);
  });
});

describe('同じ接続での次の試合', () => {
  const OTHER: LanSettings = {
    match: defaultMatchConfig(99, ['mole', 'frog', 'rabbit', 'elephant']),
    cpu: ['oni', 'oni', 'oni', 'oni'],
  };

  /** 試合が決まったかを、テストの側で決められる端末。決めた印は、次の試合を作るたびに戻る。 */
  function switchable(): { client: LockstepClient; sent: PeerMessage[]; finish: () => void } {
    let finished = false;
    const base = hooksWith(() => IDLE_INPUT);
    const hooks: LanHooks = {
      ...base,
      createSession: (settings) => {
        finished = false;
        const session = new GameSession(settings.match);
        return {
          get world() {
            return session.world;
          },
          match: {
            get finished() {
              return finished || session.match.finished;
            },
          },
          tick: () => session.tick(),
          attach: (source) => session.attach(source),
          get elapsed() {
            return session.elapsed;
          },
        };
      },
    };
    const sent: PeerMessage[] = [];
    return { client: new LockstepClient({ send: (m) => sent.push(m) }, hooks), sent, finish: () => (finished = true) };
  }

  it('試合が決まったあとだけ、ホストは次の試合の合図を送れる', () => {
    const host = switchable();
    host.client.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    host.client.receive(text({ t: 'start', seats: [0], config: SETTINGS, match: 1 }));
    // 試合の最中は送らない（幕の「もういっかい」は、試合が決まってから出る）。
    expect(host.client.requestStart(OTHER)).toBe(false);
    host.finish();
    expect(host.client.requestStart(OTHER)).toBe(true);
    expect(host.sent.at(-1)).toEqual({ t: 'start', config: OTHER });

    const guest = switchable();
    guest.client.receive(text({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    guest.client.receive(text({ t: 'start', seats: [0, 1], config: SETTINGS, match: 1 }));
    guest.finish();
    expect(guest.client.requestStart(OTHER)).toBe(false);
  });

  it('ずれが知らされた試合では、決まっていても次の試合の合図を送らない', () => {
    // どの端末の決着が正しいか分からない。続けるなら、全員が閉じて開き直す。
    const host = switchable();
    host.client.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    host.client.receive(text({ t: 'start', seats: [0], config: SETTINGS, match: 1 }));
    host.finish();
    host.client.receive(text({ t: 'desync', tick: 19, reports: [] }));
    const before = host.sent.length;
    expect(host.client.requestStart(OTHER)).toBe(false);
    expect(host.sent.length).toBe(before);
  });

  it('試合の最中に届いた start で、前の試合を捨てて次の試合を作る', () => {
    // 中継が次の試合を配ったら、全員がその1通から次の試合を作る。自分の試合がまだ決まっていなくても従う。
    const { client: c, sent } = switchable();
    c.receive(text({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    c.receive(text({ t: 'start', seats: [0, 1], config: SETTINGS, match: 1 }));
    if (c.phase.kind !== 'playing') throw new Error('始まっていない');
    const first = c.phase.driver;
    sent.length = 0;

    c.receive(text({ t: 'start', seats: [0, 1], config: OTHER, match: 2 }));

    if (c.phase.kind !== 'playing') throw new Error('次の試合が始まっていない');
    expect(c.phase.driver).not.toBe(first);
    expect(c.phase.settings).toEqual(OTHER);
    expect(c.phase.session.world.players.map((p) => p.animal)).toEqual(OTHER.match.animals);
    // 次の試合の最初の 3 tick を、次の試合の番号で送り直す。
    expect(sent.map((m) => (m.t === 'input' ? [m.tick, m.match] : m.t))).toEqual([
      [0, 2],
      [1, 2],
      [2, 2],
    ]);
  });

  it('前の試合の番号の入力は捨てる（届く順が入れ替わっても、次の試合を止めない）', () => {
    const { client: c } = switchable();
    c.receive(text({ t: 'welcome', seat: 1, role: 'guest', seats: [0] }));
    c.receive(text({ t: 'start', seats: [0, 1], config: SETTINGS, match: 1 }));
    c.receive(text({ t: 'start', seats: [0, 1], config: OTHER, match: 2 }));
    if (c.phase.kind !== 'playing') throw new Error('始まっていない');

    // 前の試合の tick 900 の入力。受け取ると「tick が飛んだ」として止まる。
    c.receive(text({ t: 'input', seat: 0, tick: 900, bits: 0, match: 1 }));
    c.receive(text({ t: 'input', seat: 0, tick: 0, bits: 0, match: 1 }));
    expect(c.phase.kind).toBe('playing');
    expect(c.phase.driver.waitingFor()).toEqual([0]);

    c.receive(text({ t: 'input', seat: 0, tick: 0, bits: 0, match: 2 }));
    expect(c.phase.driver.waitingFor()).toEqual([]);
  });

  it('送る要約にも、いまの試合の番号を付ける', () => {
    const { client: c, sent } = switchable();
    c.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    c.receive(text({ t: 'start', seats: [0], config: SETTINGS, match: 3 }));
    for (let i = 0; i < 20; i += 1) c.step();
    const hashes = sent.filter((m) => m.t === 'hash');
    expect(hashes.map((m) => (m.t === 'hash' ? [m.tick, m.match] : null))).toEqual([[19, 3]]);
  });
});

describe('止めるとき', () => {
  it('始まった試合の参加者に自分がいなければ止める', () => {
    const { client: c } = client();
    c.receive(text({ t: 'welcome', seat: 2, role: 'guest', seats: [0, 1] }));

    c.receive(text({ t: 'start', seats: [0, 1], config: SETTINGS, match: 1 }));

    expect(c.phase.kind).toBe('failed');
  });

  it('動物の数より多い人数で始まったら止める', () => {
    const { client: c } = client();
    c.receive(text({ t: 'welcome', seat: 0, role: 'host', seats: [] }));
    const twoAnimals = {
      match: { ...SETTINGS.match, animals: ['rabbit', 'fox'], startingHp: [6, 6] },
      cpu: ['easy', 'easy'],
    };

    c.receive(text({ t: 'start', seats: [0, 1, 2], config: twoAnimals, match: 1 }));

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
    c.receive(text({ t: 'start', seats: [0, 1], config: SETTINGS, match: 1 }));

    c.receive(text({ t: 'input', seat: 1, tick: 5, bits: 0, match: 1 }));

    expect(c.phase).toMatchObject({ kind: 'failed', reason: expect.stringContaining('順が乱れた') });
    // 原因を調査できるように、元の例外も残す。
    expect(c.phase.kind === 'failed' && c.phase.cause).toBeInstanceOf(Error);
    expect(c.step()).toBeNull();
  });

  it('中継との接続が切れたら止める', () => {
    const { client: c } = client();
    c.disconnected();
    expect(c.phase.kind).toBe('failed');
  });
});
