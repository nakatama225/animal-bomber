import { describe, expect, it } from 'vitest';

import { IntentGatherer } from '../../src/domain/intent/IntentSource.js';
import { createWorld, hashWorld } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { InputLog, ReplayIntentSource } from '../../src/net/InputLog.js';
import { GameSpeed, TickAccumulator } from '../../src/platform/FrameLoop.js';
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
  const clock = { elapsed: 0 };
  const gatherer = new IntentGatherer();
  for (const player of world.players) gatherer.add(new ReplayIntentSource(player.id, log, clock));

  const sim = new Simulation();
  while (clock.elapsed < TOTAL_TICKS) {
    const batch = Math.min(ticksPerFrame, TOTAL_TICKS - clock.elapsed);
    for (let i = 0; i < batch; i += 1) {
      sim.step(world, gatherer.gather(world));
      clock.elapsed += 1;
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
    const clock = { elapsed: 0 };
    const gatherer = new IntentGatherer();
    for (const player of world.players) gatherer.add(new ReplayIntentSource(player.id, log, clock));
    const sim = new Simulation();
    for (; clock.elapsed < 100; clock.elapsed += 1) sim.step(world, gatherer.gather(world));
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

describe('ゲームの速さ', () => {
  /** `take()` を n 回呼んだ結果の並び。 */
  const takes = (speed: GameSpeed, n: number): number[] => Array.from({ length: n }, () => speed.take());

  it('等倍では、1回の呼び出しで 1 tick 進む', () => {
    expect(takes(new GameSpeed(), 4)).toEqual([1, 1, 1, 1]);
  });

  it('倍率ぶんの tick を進め、端数は次へ持ち越す', () => {
    const half = new GameSpeed();
    half.set(0.5);
    expect(takes(half, 4)).toEqual([0, 1, 0, 1]);

    const quick = new GameSpeed();
    quick.set(1.25);
    expect(takes(quick, 8)).toEqual([1, 1, 1, 2, 1, 1, 1, 2]);

    const triple = new GameSpeed();
    triple.set(3);
    expect(takes(triple, 2)).toEqual([3, 3]);
  });

  it('長く回しても、進んだ tick の合計は倍率どおり（端数の誤差が積もらない）', () => {
    const speed = new GameSpeed();
    speed.set(1.75);
    let total = 0;
    for (let i = 0; i < 60_000; i += 1) total += speed.take();
    expect(total).toBe(105_000);
  });

  it('描く位置の補間に渡す進み具合は、どの倍率でも試合の時間を戻さない', () => {
    // 画面が 120Hz なら、1 tick ぶんの時間に2枚描く（実時間の alpha は 0.5 と 0）。
    // 「進めた tick の数 + 進み具合」が描いた時点の試合の時間で、これが前の1枚より戻ると、
    // 位置も絵の揺れも前へ戻って見える。
    for (const rate of [0.5, 0.75, 1, 1.25, 2, 3]) {
      const speed = new GameSpeed();
      speed.set(rate);
      let taken = 0;
      const times: number[] = [];
      for (let i = 0; i < 40; i += 1) {
        times.push(taken + speed.progress(0.5));
        taken += speed.take();
        times.push(taken + speed.progress(0));
      }
      const backward = times.flatMap((time, i) => (i > 0 && time < times[i - 1]! ? [i] : []));
      expect(backward, `${rate}倍`).toEqual([]);
    }
  });

  it('1倍より遅いときは、tick を進めない回も進み具合が進む', () => {
    // 0.5倍では、進める回と進めない回が交互に来る。進めない回に進み具合を 0 に戻すと、
    // 1 tick ぶんの動きを2回に分けて見せられず、止まる・進むを繰り返して見える。
    const half = new GameSpeed();
    half.set(0.5);
    expect(half.take()).toBe(0);
    expect(half.progress(0)).toBe(0.5);
    expect(half.progress(0.5)).toBe(0.75);
    expect(half.take()).toBe(1);
    expect(half.progress(0)).toBe(0);
  });

  it('1倍より速いときは、進み具合を 1 で止める（1つ前の tick の位置からしか埋められない）', () => {
    // 1回で2 tick 以上進んでも、描く側は1つ前の tick の位置しか覚えていない。1 を超えて渡すと、
    // いまの位置を通り越した先に描き、次の tick で止まった人が戻って見える。
    const triple = new GameSpeed();
    triple.set(3);
    triple.take();
    expect(triple.progress(0.9)).toBe(1);
    const double = new GameSpeed();
    double.set(2);
    double.take();
    expect(double.progress(0.25)).toBe(0.5);
    expect(double.progress(0.75)).toBe(1);
  });

  it('範囲の外と、刻みに乗らない値にはできない', () => {
    const speed = new GameSpeed();
    for (const rate of [0.25, 3.25, 1.1, Number.NaN]) {
      expect(() => speed.set(rate), String(rate)).toThrow('ゲームの速さにできない値');
    }
    // できなかったときは、前の倍率のまま。
    expect(speed.rate).toBe(1);
  });
});
