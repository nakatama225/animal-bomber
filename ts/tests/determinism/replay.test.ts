import { describe, expect, it } from 'vitest';

import { CpuIntentSource, cpuSeed } from '../../src/ai/CpuIntentSource.js';
import { CPU_LEVELS } from '../../src/ai/CpuLevel.js';
import { GameSession } from '../../src/app/GameSession.js';
import { IntentGatherer } from '../../src/domain/intent/IntentSource.js';
import type { PlayerIntent } from '../../src/domain/intent/PlayerIntent.js';
import { secondsToTicks, tick } from '../../src/domain/core/Tick.js';
import { defaultMatchConfig } from '../../src/domain/rules/MatchConfig.js';
import { ALIVE, OUT } from '../../src/domain/state/Life.js';
import type { PlayerId } from '../../src/domain/state/PlayerState.js';
import { createWorld, hashWorld, type WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import {
  InputLog,
  RecordingIntentSource,
  ReplayIntentSource,
} from '../../src/net/InputLog.js';
import { press } from '../helpers.js';

const SEED = 4649;
const ANIMALS = ['rabbit', 'elephant'];

/** 台本どおりに操作する窓口。人間の代わり。 */
class ScriptedSource {
  constructor(
    readonly playerId: PlayerId,
    private readonly script: (tickValue: number) => PlayerIntent,
  ) {}

  next(world: Readonly<WorldState>): PlayerIntent {
    return this.script(world.now);
  }
}

/** プレイヤー0は右と左を往復し、プレイヤー1は上下に動く台本。 */
function scriptFor(playerId: PlayerId): (tickValue: number) => PlayerIntent {
  if (playerId === 0) {
    return (t) => (Math.floor(t / 37) % 2 === 0 ? press({ right: true }) : press({ left: true }));
  }
  return (t) => (Math.floor(t / 23) % 2 === 0 ? press({ down: true }) : press({ up: true }));
}

function runScripted(ticks: number): { world: WorldState; log: InputLog } {
  const world = createWorld({ seed: SEED, animals: ANIMALS });
  const log = new InputLog();
  const clock = { elapsed: 0 };
  const gatherer = new IntentGatherer();
  for (const player of world.players) {
    gatherer.add(
      new RecordingIntentSource(new ScriptedSource(player.id, scriptFor(player.id)), log, clock),
    );
  }
  const sim = new Simulation();
  for (; clock.elapsed < ticks; clock.elapsed += 1) sim.step(world, gatherer.gather(world));
  return { world, log };
}

function runFromLog(log: InputLog, ticks: number): WorldState {
  const world = createWorld({ seed: SEED, animals: ANIMALS });
  const clock = { elapsed: 0 };
  const gatherer = new IntentGatherer();
  for (const player of world.players) {
    gatherer.add(new ReplayIntentSource(player.id, log, clock));
  }
  const sim = new Simulation();
  for (; clock.elapsed < ticks; clock.elapsed += 1) sim.step(world, gatherer.gather(world));
  return world;
}

describe('リプレイ', () => {
  it('同じ種と同じ操作からは同じ状態になる', () => {
    const a = runScripted(600);
    const b = runScripted(600);
    expect(hashWorld(a.world)).toBe(hashWorld(b.world));
  });

  it('記録した操作を流し直すと、同じ状態に行き着く', () => {
    // この実装の土台。ここが崩れると通信対戦もバランス検証も成り立たない。
    const original = runScripted(600);
    const replayed = runFromLog(original.log, 600);
    expect(hashWorld(replayed)).toBe(hashWorld(original.world));
  });

  it('種が違えば違う状態になる', () => {
    // 前の確認が「どんな入力でも同じ値になる」で通ってしまわないための対照。
    const world = createWorld({ seed: SEED + 1, animals: ANIMALS });
    const other = createWorld({ seed: SEED, animals: ANIMALS });
    expect(hashWorld(world)).not.toBe(hashWorld(other));
  });

  it('記録は文字列にしても往復できる', () => {
    const original = runScripted(300);
    const restored = InputLog.decode(original.log.encode());
    expect(restored.encode()).toBe(original.log.encode());
    expect(hashWorld(runFromLog(restored, 300))).toBe(hashWorld(original.world));
  });

  it('記録は変化した時点だけを持つ', () => {
    const log = new InputLog();
    const held = press({ right: true });
    for (let t = 0; t < 100; t += 1) log.record(t, 0, held);
    // 100 tick 押しっぱなしでも、記録は1件。
    expect(log.encode()).toBe('0:0,8');
  });

  it('記録の無い時点は、何も押していない扱いになる', () => {
    const log = new InputLog();
    log.record(50, 0, press({ bomb: true }));
    expect(log.at(10, 0).bomb).toBe(false);
    expect(log.at(50, 0).bomb).toBe(true);
    expect(log.at(9999, 0).bomb).toBe(true);
    expect(log.at(50, 1).bomb).toBe(false);
  });

  it('時間を巻き戻して記録しようとしたら止まる', () => {
    const log = new InputLog();
    log.record(10, 0, press({ right: true }));
    expect(() => log.record(5, 0, press({ left: true }))).toThrow();
  });
});

describe('途中で抜けた人の記録', () => {
  it('抜けた人は変化の一覧とは別に持ち、文字列にしても往復できる', () => {
    const log = new InputLog();
    log.record(0, 0, press({ right: true }));
    log.record(0, 1, press({ down: true }));
    log.depart(40, 1);
    // 入力が1つも配られないうちに抜けた人（変化の一覧に居ない）も落とさない。
    log.depart(-1, 2);

    const restored = InputLog.decode(log.encode());
    expect(restored.departedAfter(1)).toBe(40);
    expect(restored.departedAfter(2)).toBe(-1);
    expect(restored.departedAfter(0)).toBeUndefined();
    expect(restored.encode()).toBe(log.encode());
  });

  it.each([
    ['tick が数でない', 'departed:1,abc'],
    ['tick が小数', 'departed:1,5.5'],
    ['tick が -1 より小さい', 'departed:1,-2'],
    ['番号が無い', 'departed:,5'],
    ['番号が数でない', 'departed:x,5'],
    ['番号が 0〜3 の外', 'departed:4,5'],
    ['区画が空', '0:0,8|departed:'],
    ['同じ人が区画の中に2度', 'departed:1,5;1,9'],
    ['同じ人が別の区画に2度', '0:0,8|departed:1,5|departed:1,7'],
  ])('抜けた人の区画が読めなければ、戻す前に止まる（%s）', (_case, text) => {
    // 黙って読み飛ばしたり、あとの値で上書きしたりすると、例外も出ずに別の試合になる。
    expect(() => InputLog.decode(text)).toThrow(/抜けた/);
  });

  it('抜けた人の区画が無い文字列は、誰も抜けていない記録になる', () => {
    const restored = InputLog.decode(runScripted(300).log.encode());
    for (const id of [0, 1, 2, 3] as const) expect(restored.departedAfter(id)).toBeUndefined();
  });

  it('同じ人が抜けたことを2度記録しようとしたら止まる', () => {
    const log = new InputLog();
    log.depart(40, 1);
    expect(() => log.depart(50, 1)).toThrow(/2度/);
    expect(log.departedAfter(1)).toBe(40);
  });

  it('再生の窓口は、departedAfter の次の tick から代わりの窓口に任せ、代わりの窓口は1度だけ作る', () => {
    const log = new InputLog();
    log.record(0, 1, press({ right: true }));
    log.depart(5, 1);
    const clock = { elapsed: 0 };
    let made = 0;
    const source = new ReplayIntentSource(1, log, clock, (playerId) => {
      made += 1;
      return new ScriptedSource(playerId, () => press({ up: true }));
    });
    const world = createWorld({ seed: SEED, animals: ANIMALS });

    clock.elapsed = 5;
    expect(source.next(world)).toEqual(press({ right: true }));
    expect(made).toBe(0);
    clock.elapsed = 6;
    expect(source.next(world)).toEqual(press({ up: true }));
    clock.elapsed = 7;
    source.next(world);
    // CPU は考えた内容を覚えているので、作り直すと本物の端末とは別の手を指す。
    expect(made).toBe(1);
  });

  it('抜けた人の記録があるのに代わりの窓口の作り方が無ければ、再生を始める前に止まる', () => {
    const log = new InputLog();
    log.depart(5, 1);
    expect(() => new ReplayIntentSource(1, log, { elapsed: 0 })).toThrow(/代わりの窓口/);
    // 抜けていない人は、作り方が無くてよい（1台の試合の記録と同じ）。
    expect(() => new ReplayIntentSource(0, log, { elapsed: 0 })).not.toThrow();
  });
});

describe('ラウンドをまたぐ記録の再生', () => {
  it('ラウンドをまたいでも、記録を流し直すと同じ試合になる', () => {
    // 盤面の時刻（world.now）はラウンドごとに 0 へ戻るので、同じ時刻が試合の中で何度も現れる。
    // 記録の時刻にそれを使うと、2ラウンド目の再生で1ラウンド目の操作を引いてしまう。
    const config = {
      ...defaultMatchConfig(SEED, ['rabbit', 'elephant', 'fox', 'frog']),
      winsToTake: 2,
      roundLimit: secondsToTicks(60),
    };
    const log = new InputLog();
    const original = new GameSession(config);
    for (const player of original.world.players) {
      const cpu = new CpuIntentSource(player.id, CPU_LEVELS.hard, cpuSeed(config.seed, player.id));
      original.attach(new RecordingIntentSource(cpu, log, original));
    }
    let ticks = 0;
    let roundsEnded = 0;
    while (!original.match.finished && ticks < 60_000) {
      roundsEnded += original.tick().filter((event) => event.type === 'roundEnded').length;
      ticks += 1;
    }
    // 前提：試合が終わり、ラウンドが2つ以上あった。1ラウンドだけだと、盤面の時刻と
    // 試合通算の時刻が同じ値になり、このテストは違いを見分けない。
    expect(original.match.finished).toBe(true);
    expect(roundsEnded).toBeGreaterThanOrEqual(2);

    const replay = new GameSession(config);
    for (const player of replay.world.players) {
      replay.attach(new ReplayIntentSource(player.id, log, replay));
    }
    for (let i = 0; i < ticks; i += 1) replay.tick();

    expect(replay.match.finished).toBe(true);
    expect([...replay.match.wins]).toEqual([...original.match.wins]);
    expect(hashWorld(replay.world)).toBe(hashWorld(original.world));
  }, 60_000);
});

describe('状態の要約', () => {
  it('プレイヤーが動けば変わる', () => {
    const world = createWorld({ seed: SEED, animals: ANIMALS });
    const before = hashWorld(world);
    world.players[0]!.position = { x: 1.6, y: 1.5 };
    expect(hashWorld(world)).not.toBe(before);
  });

  it('わずかな位置のずれも見逃さない', () => {
    // 丸めてから要約すると、小さなずれが埋もれる。ずれは小さいうちに
    // 見つけたいので、小数はビットのまま混ぜている。
    const world = createWorld({ seed: SEED, animals: ANIMALS });
    const before = hashWorld(world);
    world.players[0]!.position = { x: 1.5 + 1e-9, y: 1.5 };
    expect(hashWorld(world)).not.toBe(before);
  });

  it('盤面が変われば変わる', () => {
    const world = createWorld({ seed: SEED, animals: ANIMALS });
    const before = hashWorld(world);
    world.board.set({ col: 5, row: 5 }, 'empty');
    world.board.set({ col: 5, row: 5 }, 'soft');
    world.board.set({ col: 7, row: 5 }, 'empty');
    expect(hashWorld(world)).not.toBe(before);
  });

  it('乱数を余計に引けば変わる', () => {
    // 見た目の処理がルールの乱数を引いてしまった場合を捕まえる。
    const world = createWorld({ seed: SEED, animals: ANIMALS });
    const before = hashWorld(world);
    world.rng.next();
    expect(hashWorld(world)).not.toBe(before);
  });

  it('盤面にいるか退場したかが変われば変わる', () => {
    const world = createWorld({ seed: SEED, animals: ANIMALS });
    const player = world.players[0]!;
    const alive = hashWorld(world);
    player.life = OUT;
    expect(hashWorld(world)).not.toBe(alive);
    player.life = ALIVE;
    expect(hashWorld(world)).toBe(alive);
  });

  it('外周にいる間は、外周上の位置と次に撃てる時刻も見る', () => {
    // 状態の種類だけを混ぜると、外周を回る速さや撃つ間隔がずれても検出できない。
    const world = createWorld({ seed: SEED, animals: ANIMALS });
    const player = world.players[0]!;
    player.life = { kind: 'negibon', along: 3, readyAt: tick(10) };
    const base = hashWorld(world);
    player.life = { kind: 'negibon', along: 3 + 1e-9, readyAt: tick(10) };
    expect(hashWorld(world)).not.toBe(base);
    player.life = { kind: 'negibon', along: 3, readyAt: tick(11) };
    expect(hashWorld(world)).not.toBe(base);
  });
});
