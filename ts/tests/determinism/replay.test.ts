import { describe, expect, it } from 'vitest';

import { IntentGatherer } from '../../src/domain/intent/IntentSource.js';
import type { PlayerIntent } from '../../src/domain/intent/PlayerIntent.js';
import { tick } from '../../src/domain/core/Tick.js';
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
  const gatherer = new IntentGatherer();
  for (const player of world.players) {
    gatherer.add(
      new RecordingIntentSource(new ScriptedSource(player.id, scriptFor(player.id)), log),
    );
  }
  const sim = new Simulation();
  for (let i = 0; i < ticks; i += 1) sim.step(world, gatherer.gather(world));
  return { world, log };
}

function runFromLog(log: InputLog, ticks: number): WorldState {
  const world = createWorld({ seed: SEED, animals: ANIMALS });
  const gatherer = new IntentGatherer();
  for (const player of world.players) {
    gatherer.add(new ReplayIntentSource(player.id, log));
  }
  const sim = new Simulation();
  for (let i = 0; i < ticks; i += 1) sim.step(world, gatherer.gather(world));
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
