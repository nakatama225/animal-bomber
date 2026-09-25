import { describe, expect, it } from 'vitest';

import { IntentGatherer } from '../../src/domain/intent/IntentSource.js';
import { createWorld, hashWorld } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { InputLog, ReplayIntentSource } from '../../src/net/InputLog.js';
import { TickAccumulator } from '../../src/platform/FrameLoop.js';
import { press } from '../helpers.js';

const SEED = 20260925;
const ANIMALS = ['rabbit', 'elephant'];
const TOTAL_TICKS = 600;

/** 往復する操作を記録として用意する。 */
function makeLog(): InputLog {
  const log = new InputLog();
  for (let t = 0; t < TOTAL_TICKS; t += 1) {
    log.record(t, 0, Math.floor(t / 31) % 2 === 0 ? press({ right: true }) : press({ left: true }));
    log.record(t, 1, Math.floor(t / 17) % 2 === 0 ? press({ up: true }) : press({ down: true }));
  }
  return log;
}

/**
 * 同じ記録を、1回の描画あたり `ticksPerFrame` ずつ進めて流す。
 *
 * 描画の区切りは状態に触れないので、結果は区切り方に依存しないはず。
 */
function runWithPacing(log: InputLog, ticksPerFrame: number): number {
  const world = createWorld({ seed: SEED, animals: ANIMALS });
  const gatherer = new IntentGatherer();
  for (const player of world.players) gatherer.add(new ReplayIntentSource(player.id, log));

  const sim = new Simulation();
  let done = 0;
  while (done < TOTAL_TICKS) {
    const batch = Math.min(ticksPerFrame, TOTAL_TICKS - done);
    for (let i = 0; i < batch; i += 1) {
      sim.step(world, gatherer.gather(world));
      done += 1;
    }
    // ここに描画が入る。状態には触れない。
  }
  return hashWorld(world);
}

/**
 * 実時間が計算に漏れていないことの確認。
 *
 * `Simulation.step()` は経過時間を引数に取らないので、構造上漏れようがない。
 * この検査は、その構造が保たれていることを確かめる。誰かが `step(dt)` の形へ
 * 戻したり、実時間から速度を計算する処理を足したりすると落ちる。
 *
 * 原型ではここが守られておらず、「倍速にすると1回のキー入力が
 * 2〜3回として処理される」という不具合が出た。
 */
describe('時間の刻み方', () => {
  it('1回の描画で何 tick 進めても結果は変わらない', () => {
    const log = makeLog();
    const baseline = runWithPacing(log, 1);
    for (const ticksPerFrame of [2, 3, 7, 15, 60]) {
      expect(runWithPacing(log, ticksPerFrame)).toBe(baseline);
    }
  });

  it('進めた tick 数が違えば結果は変わる', () => {
    // 前の確認が「何をしても同じ値」で通ってしまわないための対照。
    const log = makeLog();
    const world = createWorld({ seed: SEED, animals: ANIMALS });
    const gatherer = new IntentGatherer();
    for (const player of world.players) gatherer.add(new ReplayIntentSource(player.id, log));
    const sim = new Simulation();
    for (let i = 0; i < 100; i += 1) sim.step(world, gatherer.gather(world));
    expect(hashWorld(world)).not.toBe(runWithPacing(log, 1));
  });
});

describe('実時間から tick への換算', () => {
  it('1 tick ぶんの経過で 1 tick 進む', () => {
    const accumulator = new TickAccumulator();
    expect(accumulator.consume(1000 / 60)).toBe(1);
  });

  it('1 tick に満たない経過では進まない', () => {
    const accumulator = new TickAccumulator();
    expect(accumulator.consume(5)).toBe(0);
  });

  it('端数を持ち越すので、1秒でちょうど 60 tick 進む', () => {
    // 持ち越さずに切り捨てると、時間が少しずつ遅れていく。
    const accumulator = new TickAccumulator();
    let total = 0;
    // 実際の描画は 16.6ms 前後で揺れる。揺れても合計は合うこと。
    for (let i = 0; i < 60; i += 1) total += accumulator.consume(i % 2 === 0 ? 16 : 17.34);
    expect(total).toBe(60);
  });

  it('長く止まっていたぶんは捨てる', () => {
    // タブを裏に回して戻したときなど。全部まとめて進めると、
    // 処理が終わらないうちに次の描画が来て遅れが積み上がる。
    const accumulator = new TickAccumulator();
    expect(accumulator.consume(10_000)).toBe(15);
    // 捨てたので、次の呼び出しに持ち越されない。
    expect(accumulator.consume(0)).toBe(0);
  });

  it('次の tick までの進み具合を 0 以上 1 未満で返す', () => {
    const accumulator = new TickAccumulator();
    accumulator.consume(1000 / 60 / 2);
    expect(accumulator.alpha).toBeGreaterThan(0.4);
    expect(accumulator.alpha).toBeLessThan(0.6);
  });
});
