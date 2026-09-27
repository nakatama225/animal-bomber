import { describe, expect, it } from 'vitest';

import { GameSession } from '../../src/app/GameSession.js';
import { centerOf } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import { IdleIntentSource } from '../../src/domain/intent/IntentSource.js';
import { IDLE_INTENT, packIntent, type PlayerIntent } from '../../src/domain/intent/PlayerIntent.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import { SPAWN_CELLS } from '../../src/domain/rules/tuning.js';
import { OUT } from '../../src/domain/state/Life.js';
import type { PlayerId } from '../../src/domain/state/PlayerState.js';
import { hashWorld } from '../../src/domain/state/WorldState.js';
import { ConfirmedInputs, NetworkIntentSource } from '../../src/net/ConfirmedInputs.js';
import { ReplayIntentSource } from '../../src/net/InputLog.js';
import { lanCpuSource } from '../../src/net/lanCpu.js';
import { HASH_INTERVAL, INPUT_DELAY, LockstepDriver } from '../../src/net/LockstepDriver.js';
import type { LanSettings, PeerMessage } from '../../src/net/protocol.js';
import { press } from '../helpers.js';
import { FakeRelay, hooksWith, Peer } from './fakeRelay.js';

const ANIMALS = ['rabbit', 'elephant', 'fox', 'frog'];

function settings(overrides: Partial<LanSettings['match']> = {}): LanSettings {
  return { match: { ...defaultMatchConfig(20260927, ANIMALS), ...overrides }, cpu: ANIMALS.map(() => 'normal') };
}

/** プレイヤーごとに違う動きをする台本。爆弾も置く。 */
function wander(playerId: PlayerId, call: number): PlayerIntent {
  const period = 23 + playerId * 14;
  const phase = Math.floor(call / period) % 4;
  const bomb = call % (70 + playerId * 11) === 0;
  const moves: Partial<PlayerIntent>[] = [{ right: true }, { down: true }, { left: true }, { up: true }];
  return press({ ...moves[phase], bomb });
}

/** `count` 台をつなぎ、ホストの合図で始めたところまで。 */
function startMatch(count: number, config = settings(), script = wander): { relay: FakeRelay; peers: Peer[] } {
  const relay = new FakeRelay();
  const peers = Array.from({ length: count }, () => new Peer(relay.connect(hooksWith(script))));
  relay.deliver();
  expect(peers[0]?.client.requestStart(config)).toBe(true);
  relay.deliver();
  for (const peer of peers) expect(peer.client.phase.kind).toBe('playing');
  return { relay, peers };
}

/** 全員を1 tick ずつ進め、そのたびにメッセージを届ける。 */
function runTogether(relay: FakeRelay, peers: readonly Peer[], ticks: number): void {
  for (let i = 0; i < ticks; i += 1) {
    for (const peer of peers) peer.step();
    relay.deliver();
  }
}

/** 2台が同じ tick に同じ状態だったか。比べた tick の数も返す（0 件で「一致」としないため）。 */
function compareHashes(a: Peer, b: Peer): { mismatched: number[]; compared: number } {
  const mismatched: number[] = [];
  let compared = 0;
  for (const [t, hash] of a.hashes) {
    const other = b.hashes.get(t);
    if (other === undefined) continue;
    compared += 1;
    if (other !== hash) mismatched.push(t);
  }
  return { mismatched, compared };
}

describe('ロックステップ', () => {
  it('2台が同じ入力で進め、毎 tick 同じ状態になる', () => {
    const { relay, peers } = startMatch(2);
    const [host, guest] = peers as [Peer, Peer];

    runTogether(relay, peers, 900);

    const { mismatched, compared } = compareHashes(host, guest);
    expect(compared).toBeGreaterThan(800);
    expect(mismatched).toEqual([]);
    // 中継の突き合わせも実際に行われ、全部一致している。
    expect(relay.agreed.length).toBeGreaterThanOrEqual(40);
    expect(host.client.phase.kind === 'playing' && host.client.phase.driver.desync).toBeNull();
  });

  it('相手の操作が、自分の手元の試合に届いている', () => {
    // 上の「一致」が、全員が何もしていないことで成り立っていないことの確認。
    const { relay, peers } = startMatch(2);
    const [host, guest] = peers as [Peer, Peer];
    const spawnOfGuest = { ...host.session.world.players[1]!.position };

    runTogether(relay, peers, 120);

    const onHost = host.session.world.players[1]!.position;
    expect(onHost).not.toEqual(spawnOfGuest);
    expect(onHost).toEqual(guest.session.world.players[1]!.position);
  });

  it('人間のいない枠は CPU が受け持ち、動く', () => {
    // 繋ぎ忘れても、全員の端末で同じく立ち止まるので要約は一致する。動いたかを直接見る。
    const { relay, peers } = startMatch(2);
    const [host] = peers as [Peer];
    const spawns = [2, 3].map((id) => ({ ...host.session.world.players[id]!.position }));

    runTogether(relay, peers, 120);

    const now = [2, 3].map((id) => host.session.world.players[id]!.position);
    expect(now[0]).not.toEqual(spawns[0]);
    expect(now[1]).not.toEqual(spawns[1]);
  });

  it('設定に開始位置の並びがあっても読まず、全員がプレイヤー番号の順に4隅から始まる', () => {
    // 原型の通信対戦（setupPlayersLan）は番号の順。並びを読むかどうかが端末ごとに違うと試合がずれる。
    // 読み取り（parseLanSettings）で読まず、ホストも含めて全員が、中継から届いた同じ1通から試合を作る。
    const config = settings();
    const withOrder = { ...config, match: { ...config.match, spawnOrder: [0, 3, 1, 2] } };
    const { peers } = startMatch(2, withOrder);
    for (const peer of peers) {
      expect(peer.session.world.players.map((player) => player.position)).toEqual(SPAWN_CELLS.map(centerOf));
    }
  });

  it('押した操作は、3 tick 遅れて効く', () => {
    // 21 回目に読まれた（= tick 20 を進めたときの）操作だけ爆弾を押す。0 回目は始まったときに読まれる。
    const script = (_id: PlayerId, call: number): PlayerIntent => press({ bomb: call === 21 });
    const { relay, peers } = startMatch(2, settings(), script);
    const [host] = peers as [Peer];

    runTogether(relay, peers, 30);

    const phase = host.client.phase;
    if (phase.kind !== 'playing') throw new Error('始まっていない');
    const log = phase.driver.log;
    expect(log.at(20 + INPUT_DELAY - 1, 0).bomb).toBe(false);
    expect(log.at(20 + INPUT_DELAY, 0).bomb).toBe(true);
    expect(log.at(20 + INPUT_DELAY + 1, 0).bomb).toBe(false);
  });

  it('押したまま始まった爆弾と技のボタンは、1ラウンド目でも離すまで効かない', () => {
    // ⚠️ 最初の INPUT_DELAY tick を何もしない意思で埋めると、tick 0 に「離した」が届き、
    // tick 3 に押していた内容が「押した瞬間」として届いて、押したまま始まった人が開始位置に爆弾を置く。
    // ホストが Enter で「はじめる」を押し、その Enter がまだ押されている、という普通の始め方で起きる。
    // この台本では2人とも押しているので、2人とも置く。
    const held = press({ bomb: true, action: true });
    // 0〜9 回目は押したまま、10・11 回目で離し、12 回目から押し直す。
    const script = (_id: PlayerId, call: number): PlayerIntent =>
      call < 10 ? held : call < 12 ? IDLE_INTENT : press({ bomb: true });
    const { relay, peers } = startMatch(2, settings(), script);
    const [host] = peers as [Peer];
    const bombsOfHumans = (): number => host.session.world.bombs.filter((bomb) => bomb.owner <= 1).length;

    for (let t = 0; t < 12; t += 1) {
      runTogether(relay, peers, 1);
      expect(bombsOfHumans(), `tick ${t}`).toBe(0);
      for (const id of [0, 1] as const) {
        expect(host.session.world.players[id]!.actionHeld, `tick ${t} のプレイヤー ${id}`).toBe(-1);
      }
    }
    // 離して押し直せば置ける（入力を殺していないことの確認）。
    runTogether(relay, peers, 8);
    expect(bombsOfHumans()).toBe(2);
  });

  it('相手の入力が届くまでは進めずに待つ', () => {
    const { relay, peers } = startMatch(2);
    const [host, guest] = peers as [Peer, Peer];

    // ゲストが進めないので、ゲストの入力は最初に埋めた 3 tick ぶんしか無い。
    for (let i = 0; i < INPUT_DELAY; i += 1) expect(host.step()).toBe(true);
    expect(host.step()).toBe(false);
    expect(host.session.elapsed).toBe(INPUT_DELAY);
    const phase = host.client.phase;
    expect(phase.kind === 'playing' && phase.driver.waitingFor()).toEqual([1]);

    // ゲストが1つ進めて入力が届けば、ホストも1つ進める。
    expect(guest.step()).toBe(true);
    relay.deliver();
    expect(host.step()).toBe(true);
    expect(host.step()).toBe(false);
  });

  it('進める速さが端末ごとに違っても、同じ試合になる', () => {
    // 片方は1回に最大7 tick、もう片方は1 tick。速いほうは相手を待って止まりながら進む。
    const { relay, peers } = startMatch(2);
    const [fast, slow] = peers as [Peer, Peer];

    // ⚠️ 回数に上限を置く。どちらも進めなくなる不具合が入ったとき、テストが終わらなくなる。
    for (let round = 0; round < 2000 && slow.session.elapsed < 600; round += 1) {
      for (let i = 0; i < 7; i += 1) fast.step();
      slow.step();
      relay.deliver();
    }
    expect(slow.session.elapsed).toBe(600);

    const { mismatched, compared } = compareHashes(fast, slow);
    expect(compared).toBeGreaterThanOrEqual(600);
    expect(mismatched).toEqual([]);
    expect(fast.session.elapsed - slow.session.elapsed).toBeLessThanOrEqual(INPUT_DELAY);
  });

  it('試合が実際に使った操作は、その tick に届いた操作と同じ（2ラウンド目以降も）', () => {
    // 全端末が同じく時刻を取り違えると（ラウンドごとに 0 へ戻る world.now で引く、など）、
    // 要約は一致したまま、押したキーが効かなくなる。要約の比較では見つからないので、
    // 試合が実際に使った操作（previousIntent）を、届いた操作の記録と tick ごとに比べる。
    const config = settings({ roundLimit: tick(240), suddenDeath: false });
    const { relay, peers } = startMatch(2, config);
    const [host, guest] = peers as [Peer, Peer];
    let laterRounds = 0;

    for (let i = 0; i < 1500; i += 1) {
      const t = host.driver.elapsed;
      const waiting = host.session.betweenRounds;
      const stepped = host.step();
      guest.step();
      relay.deliver();
      // 決着のあとの待ちの tick は操作を使わない（盤面を止めている）。
      if (!stepped || waiting || host.session.betweenRounds) continue;
      for (const id of [0, 1] as const) {
        const used = packIntent(host.session.world.players[id]!.previousIntent);
        expect(used, `tick ${t} のプレイヤー ${id}`).toBe(packIntent(host.driver.log.at(t, id)));
      }
      if (host.session.match.round >= 2) laterRounds += 1;
    }

    // 1ラウンド目は world.now と通算の tick が一致するので、取り違えは2ラウンド目以降でしか見えない。
    expect(laterRounds).toBeGreaterThan(100);
  });

  it('通信対戦の記録を1台で流し直すと、同じ試合になる（ラウンドをまたいでも）', () => {
    // 届いた入力の記録と、記録を流す窓口は、どちらも試合通算の tick で引く。
    const config = settings({ roundLimit: tick(240), suddenDeath: false });
    const { relay, peers } = startMatch(2, config);
    const [host] = peers as [Peer, Peer];
    runTogether(relay, peers, 1500);
    // 前提：ラウンドが入れ替わっている。1ラウンドだけだと、盤面の時刻と通算の tick が同じ値になる。
    expect(host.session.match.round).toBeGreaterThanOrEqual(3);

    const replay = new GameSession(config.match);
    for (const id of [0, 1] as const) {
      replay.attach(new ReplayIntentSource(id, host.driver.log, replay));
    }
    // CPU の枠の操作は記録に無い。本物の端末と同じ設定から作り直す。
    for (const id of [2, 3] as const) replay.attach(lanCpuSource(id, config));

    // 最後の盤面だけを比べると、最後のラウンドしか見ないことになる（この設定では、
    // 途中のラウンドは時間切れの引き分けで、勝ち数にも差が出ない）。tick ごとに比べる。
    const mismatched: number[] = [];
    let compared = 0;
    // 再生の側の試合が先に終わると elapsed が進まなくなるので、回数に上限を置く。
    for (let guard = 0; replay.elapsed < host.session.elapsed && guard < 10_000; guard += 1) {
      const t = replay.elapsed;
      replay.tick();
      const expected = host.hashes.get(t);
      if (expected === undefined) continue;
      compared += 1;
      if (hashWorld(replay.world) !== expected) mismatched.push(t);
    }
    expect(compared).toBeGreaterThan(1400);
    expect(mismatched).toEqual([]);
  });

  it('ラウンドをまたいでも（決着のあとの待ちを含めて）同じ試合が続く', () => {
    // 時間切れを早め、延長戦を切って、ラウンドが何度も入れ替わるようにする。
    const config = settings({ roundLimit: tick(240), suddenDeath: false });
    const { relay, peers } = startMatch(2, config);
    const [host, guest] = peers as [Peer, Peer];

    runTogether(relay, peers, 1500);

    expect(host.session.match.round).toBeGreaterThanOrEqual(3);
    expect(guest.session.match.round).toBe(host.session.match.round);
    expect(compareHashes(host, guest).mismatched).toEqual([]);
  });

  it('4台でも同じ試合になる', () => {
    const { relay, peers } = startMatch(4);

    runTogether(relay, peers, 600);

    const [first, ...rest] = peers as [Peer, ...Peer[]];
    for (const other of rest) {
      const { mismatched, compared } = compareHashes(first, other);
      // 比べた件数も見る。1 tick も進まなくても「食い違い 0 件」になるため。
      expect(compared).toBeGreaterThanOrEqual(590);
      expect(mismatched).toEqual([]);
    }
  });
});

describe('ずれを見つける', () => {
  it('1台の状態だけが変わったら、次の突き合わせで全員が止まる', () => {
    const { relay, peers } = startMatch(2);
    const [host, guest] = peers as [Peer, Peer];
    runTogether(relay, peers, 50);

    // 不具合の代わりに、ゲストの手元でだけ試合を書き換える。
    guest.session.world.players[0]!.hp -= 1;
    runTogether(relay, peers, HASH_INTERVAL * 2);

    for (const peer of [host, guest]) {
      const phase = peer.client.phase;
      if (phase.kind !== 'playing') throw new Error('始まっていない');
      expect(phase.driver.desync?.tick).toBe(59);
      // ずれたあとは進めない。
      expect(peer.step()).toBe(false);
    }
  });

  it.each([
    // 4人のうち3人を退場させると、残った1人の勝ちで試合が終わる（1勝で優勝の設定）。
    ['片方だけ試合が終わる', [[1, 2, 3], []]],
    ['両方終わるが、勝者が違う', [[1, 2, 3], [0, 2, 3]]],
  ] as const)('試合を決める決着が端末ごとに食い違っても、次の突き合わせで止まる: %s', (_label, downed) => {
    // 終わった端末が交換をやめると、突き合わせが揃わずに、ずれが見つからない。
    const { relay, peers } = startMatch(2, settings({ winsToTake: 1 }));
    const [host, guest] = peers as [Peer, Peer];
    runTogether(relay, peers, 45);

    // 不具合の代わりに、端末ごとに違うプレイヤーを倒す。
    const [onGuest, onHost] = downed;
    for (const id of onGuest) guest.session.world.players[id]!.life = OUT;
    for (const id of onHost) host.session.world.players[id]!.life = OUT;
    runTogether(relay, peers, HASH_INTERVAL * 2);

    expect(guest.session.match.finished).toBe(true);
    for (const peer of [host, guest]) expect(peer.driver.desync?.tick).toBe(59);
  });

  it('試合が終わったあとも、要約の突き合わせを続ける', () => {
    const { relay, peers } = startMatch(2, settings({ winsToTake: 1 }));
    const [host, guest] = peers as [Peer, Peer];
    runTogether(relay, peers, 10);
    for (const peer of peers) {
      for (const id of [1, 2, 3]) peer.session.world.players[id]!.life = OUT;
    }

    runTogether(relay, peers, HASH_INTERVAL * 3);

    expect(host.session.match.finished && guest.session.match.finished).toBe(true);
    expect(host.driver.elapsed).toBe(10 + HASH_INTERVAL * 3);
    expect(relay.agreed).toEqual([19, 39, 59]);
  });

  it('要約と一緒に、試合の乱数を引いた回数も送る', () => {
    const sent: PeerMessage[] = [];
    const session = new GameSession(settings().match);
    const driver = new LockstepDriver({
      session,
      link: { send: (m) => sent.push(m) },
      localId: 0,
      local: new IdleIntentSource(0),
      humans: [0],
      replacement: (id) => new IdleIntentSource(id),
    });
    for (const id of [1, 2, 3] as const) session.attach(new IdleIntentSource(id));
    driver.start();
    for (let i = 0; i < HASH_INTERVAL; i += 1) driver.step();

    const report = sent.find((m) => m.t === 'hash');
    expect(report).toEqual({
      t: 'hash',
      tick: HASH_INTERVAL - 1,
      hash: hashWorld(session.world),
      rngCalls: session.world.rng.calls,
    });
  });
});

describe('抜けた人', () => {
  it('抜けた人は、全員の手元で同じ tick から CPU に替わる', () => {
    const { relay, peers } = startMatch(3);
    const [host, guest, leaver] = peers as [Peer, Peer, Peer];
    runTogether(relay, peers, 200);

    relay.leave(2);
    // 抜けた直後の数 tick は、届いていた本人の操作で動く。CPU に替わってから控える。
    runTogether(relay, [host, guest], INPUT_DELAY + 1);
    const before = { ...host.session.world.players[2]!.position };
    runTogether(relay, [host, guest], 400 - INPUT_DELAY - 1);

    expect(compareHashes(host, guest).mismatched).toEqual([]);
    expect(host.session.elapsed).toBeGreaterThan(leaver.session.elapsed + 300);
    // 抜けた人の動物は止まらずに動き続ける（CPU が受け持っている）。
    expect(host.session.world.players[2]!.position).not.toEqual(before);
    const phase = host.client.phase;
    expect(phase.kind === 'playing' && phase.driver.waitingFor()).toEqual([]);
  });

  it('抜けた知らせと最後の入力の届く順が端末ごとに違っても、同じ試合になる', () => {
    const lastTick = 10;
    const make = (): { session: GameSession; driver: LockstepDriver } => {
      const session = new GameSession(settings().match);
      const driver = new LockstepDriver({
        session,
        link: { send: () => undefined },
        localId: 0,
        local: new IdleIntentSource(0),
        humans: [0, 1],
        replacement: (id) => new IdleIntentSource(id),
      });
      for (const id of [2, 3] as const) session.attach(new IdleIntentSource(id));
      driver.start();
      return { session, driver };
    };
    const right = { t: 'input', seat: 1, bits: 8 } as const;
    const a = make();
    const b = make();

    // a は最後の入力のあとに知らせを、b は知らせのあとに最後の入力を受け取る。
    for (let t = 0; t < lastTick; t += 1) {
      a.driver.receive({ ...right, tick: t });
      b.driver.receive({ ...right, tick: t });
    }
    a.driver.receive({ ...right, tick: lastTick });
    a.driver.receive({ t: 'peer_left', seat: 1, lastTick });
    b.driver.receive({ t: 'peer_left', seat: 1, lastTick });
    // 知らせが来ても、lastTick までの入力はまだ要るので待つ。
    let guard = 0;
    while (b.driver.step() !== null && guard < 30) guard += 1;
    expect(b.session.elapsed).toBe(lastTick);
    b.driver.receive({ ...right, tick: lastTick });

    for (const peer of [a, b]) {
      while (peer.session.elapsed < 60) expect(peer.driver.step()).not.toBeNull();
    }
    expect(hashWorld(b.session.world)).toBe(hashWorld(a.session.world));
  });

  it('lastTick より後に届いた入力は、全員が同じく捨てる', () => {
    const session = new GameSession(settings().match);
    const driver = new LockstepDriver({
      session,
      link: { send: () => undefined },
      localId: 0,
      local: new IdleIntentSource(0),
      humans: [0, 1],
      replacement: (id) => new IdleIntentSource(id),
    });
    driver.start();
    driver.receive({ t: 'peer_left', seat: 1, lastTick: -1 });

    expect(() => driver.receive({ t: 'input', seat: 1, tick: 0, bits: 8 })).not.toThrow();
    expect(driver.log.at(0, 1)).toEqual(IDLE_INTENT);
  });
});

describe('届いた入力', () => {
  it('まだ届いていない tick を読もうとしたら止まる', () => {
    // 記録の無い tick に「直前の意思が続いている」を返すと、届く前に進めても気づけない。
    const inputs = new ConfirmedInputs();
    inputs.put(1, 0, press({ right: true }));
    const source = new NetworkIntentSource(1, inputs, { elapsed: 1 });

    expect(() => source.next()).toThrow(/まだ届いていない/);
  });

  it('tick が飛んだ入力は受け取らない', () => {
    const inputs = new ConfirmedInputs();
    inputs.put(1, 0, IDLE_INTENT);

    expect(() => inputs.put(1, 2, IDLE_INTENT)).toThrow(/順が乱れた/);
    expect(() => inputs.put(1, 0, IDLE_INTENT)).toThrow(/順が乱れた/);
    expect(inputs.through(1)).toBe(0);
  });

  it('自分の入力が中継から返ってきたら止まる', () => {
    const session = new GameSession(settings().match);
    const driver = new LockstepDriver({
      session,
      link: { send: () => undefined },
      localId: 0,
      local: new IdleIntentSource(0),
      humans: [0, 1],
      replacement: (id) => new IdleIntentSource(id),
    });

    expect(() => driver.receive({ t: 'input', seat: 0, tick: 0, bits: 0 })).toThrow(/自分の入力/);
    expect(() => driver.receive({ t: 'input', seat: 2, tick: 0, bits: 0 })).toThrow(/人間ではない/);
  });

  it('試合の途中からは始められない', () => {
    const session = new GameSession(settings().match);
    session.tick();

    expect(
      () =>
        new LockstepDriver({
          session,
          link: { send: () => undefined },
          localId: 0,
          local: new IdleIntentSource(0),
          humans: [0],
          replacement: (id) => new IdleIntentSource(id),
        }),
    ).toThrow(/最初から/);
  });
});
