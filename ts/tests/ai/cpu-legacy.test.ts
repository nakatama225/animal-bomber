import { describe, expect, it } from 'vitest';

import { CpuContext } from '../../src/ai/CpuContext.js';
import { CpuInputSource } from '../../src/ai/CpuInputSource.js';
import { CPU_LEVELS, type CpuLevelKey } from '../../src/ai/CpuLevel.js';
import { freshMemory, type CpuMemory } from '../../src/ai/CpuMemory.js';
import { FLEE } from '../../src/ai/behaviors/Flee.js';
import { HUNT } from '../../src/ai/behaviors/Hunt.js';
import { WANDER } from '../../src/ai/behaviors/Wander.js';
import { centerOf, type Cell } from '../../src/domain/core/Coord.js';
import { Rng } from '../../src/domain/core/Rng.js';
import { tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { IDLE_INPUT, type PlayerInput } from '../../src/domain/input/PlayerInput.js';
import { placeBombAt } from '../../src/domain/mutations/bombs.js';
import { DangerMap } from '../../src/domain/query/DangerMap.js';
import type { PlayerState } from '../../src/domain/state/PlayerState.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { clearBoard, grantSpecial, makeWorld } from '../helpers.js';

/*
 * CPU を原型（legacy/animal-bomber.html の cpuUpdate・planCPU）に合わせた所。
 *
 * 原型の CPU は、ボタンを通らずに関数を直に呼んでいた。この版の CPU は入力しか返せないので、
 * とくぎは「とくぎを直に出すボタン」（`PlayerInput.special`）で出す。
 */

interface Duel {
  readonly world: WorldState;
  readonly me: PlayerState;
  readonly foe: PlayerState;
  readonly source: CpuInputSource;
  readonly sim: Simulation;
}

/** 壊せるブロックを除いた盤面で、プレイヤー 0 を CPU、1 を何もしないプレイヤーにする。 */
function duel(animal: string, at: Cell, foeAt: Cell, level: CpuLevelKey = 'hard', other = 'rabbit'): Duel {
  const world = makeWorld(3, [animal, other]);
  clearBoard(world);
  world.items = [];
  const [me, foe] = world.players as [PlayerState, PlayerState];
  me.position = centerOf(at);
  foe.position = centerOf(foeAt);
  return { world, me, foe, source: new CpuInputSource(0, CPU_LEVELS[level], 1), sim: new Simulation() };
}

/** 1 tick 進める。CPU の入力と、その tick のイベントを返す。 */
function step(scene: Duel): { input: PlayerInput; events: SimEvent[] } {
  const input = scene.source.next(scene.world);
  const events = scene.sim.step(scene.world, new Map([[0, input], [1, IDLE_INPUT]]));
  return { input, events };
}

describe('ぞう：危ないときに突進で逃げる（原型 cpuUpdate の `p.chicken===\'elephant\' && inDanger`）', () => {
  it('危ないマスに立っていてチキンがあれば、最初の tick に突進する。鼻水は出ず、その tick は歩かない', () => {
    const scene = duel('elephant', { col: 3, row: 7 }, { col: 19, row: 13 });
    grantSpecial(scene.me, 1);
    scene.me.facing = 'right';
    scene.foe.maxBombs = 5;
    placeBombAt(scene.world, scene.foe, { col: 3, row: 7 });
    const before = { ...scene.me.position };
    const { input, events } = step(scene);
    expect(input).toEqual({ ...IDLE_INPUT, special: true });
    expect(scene.me.action?.kind).toBe('charge');
    expect(events.filter((e) => e.type === 'techniqueUsed')).toEqual([
      { type: 'techniqueUsed', player: 0, special: true },
    ]);
    expect(scene.me.position).toEqual(before);
    expect(scene.world.bombs).toHaveLength(1);
  });

  it('危なくなければ、一直線上に相手がいても突進しない（攻めには使わない）', () => {
    const scene = duel('elephant', { col: 3, row: 7 }, { col: 7, row: 7 });
    grantSpecial(scene.me, 1);
    for (let t = 0; t < 30; t += 1) {
      const { input } = step(scene);
      expect(input.special).toBe(false);
      if (scene.world.bombs.length > 0) break;
    }
    expect(scene.me.specialCharges).toBe(1);
  });
});

describe('うさぎ・かえる・きつね：歩いて置いたあとに、とくぎを直に出す（原型 cpuUpdate の最後の分岐）', () => {
  for (const [animal, distance, out] of [
    ['rabbit', 5, 6],
    ['frog', 8, 9],
    ['fox', 6, 7],
  ] as const) {
    it(`${animal}：相手まで歩いて ${distance} マスなら出し、${out} マスなら出さない。出すときは通常技のボタンを押さない`, () => {
      const run = (gap: number): PlayerInput => {
        const scene = duel(animal, { col: 1, row: 7 }, { col: 1 + gap, row: 7 });
        grantSpecial(scene.me, 1);
        return scene.source.next(scene.world);
      };
      expect(run(distance)).toMatchObject({ special: true, action: false });
      expect(run(out).special).toBe(false);
    });
  }
});

describe('とくぎを持っているかは、回数ではなく持っている印で見る（原型 cpuUpdate は p.chicken を見る）', () => {
  /**
   * 外周から戻ったときの形にする。回数は残り、持っている印だけが外れている。原型の toNegibon（L2255）は
   * chicken だけを消して chickenCharges を残し、この版の sendToLane も同じ（tests/systems/negibon.test.ts）。
   */
  function returnedFromLane(player: PlayerState, charges: number): void {
    grantSpecial(player, charges);
    player.hasSpecial = false;
  }

  it('ぞう：危ないマスに立っていても、印が無ければ突進のボタンを押さない（原型 L1946。印があれば押す）', () => {
    const pressed = (mark: boolean): boolean => {
      const scene = duel('elephant', { col: 3, row: 7 }, { col: 19, row: 13 });
      if (mark) grantSpecial(scene.me, 2);
      else returnedFromLane(scene.me, 2);
      scene.me.facing = 'right';
      scene.foe.maxBombs = 5;
      placeBombAt(scene.world, scene.foe, { col: 3, row: 7 });
      return scene.source.next(scene.world).special;
    };
    expect(pressed(true)).toBe(true);
    expect(pressed(false)).toBe(false);
  });

  it('もぐら：相手が歩いて来られる空いたマスでも、印が無ければ掘らない（原型 L1926。印があれば掘る）', () => {
    const pressed = (mark: boolean): boolean => {
      const scene = duel('mole', { col: 5, row: 7 }, { col: 11, row: 7 });
      if (mark) grantSpecial(scene.me, 2);
      else returnedFromLane(scene.me, 2);
      return scene.source.next(scene.world).special;
    };
    expect(pressed(true)).toBe(true);
    expect(pressed(false)).toBe(false);
  });

  for (const [animal, distance, line] of [
    ['rabbit', 5, 'L2059'],
    ['frog', 8, 'L2054'],
    ['fox', 6, 'L2046'],
  ] as const) {
    it(`${animal}：相手まで歩いて ${distance} マスでも、印が無ければとくぎのボタンを押さない（原型 ${line}。印があれば押す）`, () => {
      const pressed = (mark: boolean): boolean => {
        const scene = duel(animal, { col: 1, row: 7 }, { col: 1 + distance, row: 7 });
        if (mark) grantSpecial(scene.me, 2);
        else returnedFromLane(scene.me, 2);
        return scene.source.next(scene.world).special;
      };
      expect(pressed(true)).toBe(true);
      expect(pressed(false)).toBe(false);
    });
  }

  it('かえる：回数が残っていても印が無ければ、正面のアイテムへ舌を伸ばす（原型 L1931 の `!p.chicken`。印があれば伸ばさない）', () => {
    const tongue = (mark: boolean): boolean => {
      const scene = duel('frog', { col: 1, row: 1 }, { col: 19, row: 13 });
      scene.world.items = [{ id: scene.world.ids.take(), cell: { col: 3, row: 1 }, kind: 'fire' }];
      scene.me.facing = 'right';
      if (mark) grantSpecial(scene.me, 2);
      else returnedFromLane(scene.me, 2);
      return scene.source.next(scene.world).action;
    };
    expect(tongue(true)).toBe(false);
    expect(tongue(false)).toBe(true);
  });
});

describe('きつね：爆弾を置くときは一列に並べる（原型 cpuUpdate の foxLineShot）', () => {
  it('前が空いていれば技のボタン（一列）を押す。この tick に歩く向きに並ぶ', () => {
    // 射線に相手がいて、すぐ置きたい場面。右へ一列（手持ち 2）。
    const scene = duel('fox', { col: 3, row: 1 }, { col: 5, row: 1 }, 'oni');
    scene.me.maxBombs = 2;
    scene.me.power = 3;
    scene.me.facing = 'right';
    const { input } = step(scene);
    expect([input.action, input.bomb]).toEqual([true, false]);
    expect(scene.world.bombs.map((bomb) => bomb.cell)).toEqual([
      { col: 4, row: 1 },
      { col: 5, row: 1 },
    ]);
  });

  it('歩きながら置くときは、歩いた向きに並べる（原型も経路を1歩進めて向きが変わってから並べる）', () => {
    // 上を向いて (3,1) に立ち、右の (4,1) へ歩く途中で置く。上は柱なので、向きのままなら足元に置いてしまう。
    const scene = duel('fox', { col: 3, row: 1 }, { col: 19, row: 13 });
    scene.me.facing = 'up';
    scene.source.next(scene.world);
    const memory = scene.source.memory as CpuMemory;
    memory.path = [{ col: 4, row: 1 }];
    memory.wantBomb = true;
    memory.thinkIn = 99;
    const { input } = step(scene);
    expect([input.right, input.action, input.bomb]).toEqual([true, true, false]);
    expect(scene.world.bombs.map((bomb) => bomb.cell.row)).toEqual([1, 1]);
  });

  it('前が塞がっていれば、足元に1個置く（原型の cap=0）', () => {
    const scene = duel('fox', { col: 3, row: 1 }, { col: 3, row: 3 }, 'oni');
    scene.me.power = 3;
    scene.me.facing = 'up';
    const { input } = step(scene);
    expect([input.action, input.bomb]).toEqual([false, true]);
    expect(scene.world.bombs.map((bomb) => bomb.cell)).toEqual([{ col: 3, row: 1 }]);
  });
});

describe('危ないかは、立っているマス（体の中心のマス）だけで見る（原型 cpuUpdate の `danger[ty][tx]`）', () => {
  it('中心のマスが安全なら、体が隣の危ないマスにかかっていても逃げない', () => {
    // (3,1) の右端に立つ。体は (4,1) にかかる。爆弾は (5,1)・火力 1 で (4,1) まで届く。
    const scene = duel('rabbit', { col: 3, row: 1 }, { col: 19, row: 13 });
    scene.me.position = { x: 3.9, y: 1.5 };
    scene.foe.maxBombs = 5;
    scene.foe.power = 1;
    placeBombAt(scene.world, scene.foe, { col: 5, row: 1 });
    scene.source.next(scene.world);
    expect(scene.source.memory.mode).not.toBe('flee');
    // 対照：中心が (4,1) に入っていれば逃げる。
    scene.me.position = { x: 4.1, y: 1.5 };
    const again = new CpuInputSource(0, CPU_LEVELS.hard, 1);
    again.next(scene.world);
    expect(again.memory.mode).toBe('flee');
  });
});

describe('判断の規則を原型に合わせた所', () => {
  function context(world: WorldState, at: Cell, level: CpuLevelKey = 'hard'): CpuContext {
    const me = world.players[0]!;
    me.position = centerOf(at);
    return new CpuContext(world, me, at, DangerMap.of(world), true, CPU_LEVELS[level], freshMemory(new Rng(1)), new Rng(1));
  }

  it('逃げ道が燃えているマスしか通らないなら、遠回りの段で燃えているマスを通って逃げる（原型 nearestSafePath の3段目）', () => {
    // 1行目の 1〜5 列だけが空いた通路。(1,1) に火力 1 の爆弾、(2,1) にいま爆風が乗っている。
    const world = makeWorld(3, ['rabbit', 'elephant']);
    for (const { cell, tile } of world.board.cells()) {
      if (tile !== 'hard') world.board.set(cell, 'hard');
    }
    for (let col = 1; col <= 5; col += 1) world.board.set({ col, row: 1 }, 'empty');
    const foe = world.players[1]!;
    foe.maxBombs = 5;
    foe.power = 1;
    placeBombAt(world, foe, { col: 1, row: 1 });
    world.blasts.push({ id: world.ids.take(), cell: { col: 2, row: 1 }, owner: 1, isCenter: false, remaining: tick(20) });
    const plan = FLEE.decide(context(world, { col: 1, row: 1 }));
    expect(plan?.path).toEqual([{ col: 2, row: 1 }, { col: 3, row: 1 }]);
  });

  it('相手のすぐそばまで来たら、直前に置けないと分かったあとでも、置く判断をする（原型は爆弾を控える残りを見ない）', () => {
    const world = makeWorld(3, ['rabbit', 'elephant']);
    clearBoard(world);
    world.players[1]!.position = centerOf({ col: 3, row: 1 });
    const ctx = context(world, { col: 1, row: 1 }, 'oni');
    ctx.memory.bombBan = 30;
    expect(HUNT.decide(ctx)).toMatchObject({ mode: 'hunt', wantBomb: true });
  });

  it('うろつく先の遠さは、マスを判定するたびに乱数で決め直す（原型の `d>=2+rnd(4)`）', () => {
    const world = makeWorld(3, ['rabbit', 'elephant']);
    clearBoard(world);
    const ctx = context(world, { col: 9, row: 7 });
    const before = ctx.rng.calls;
    WANDER.decide(ctx);
    // 1回きりで決めると 1 回しか取り出さない。
    expect(ctx.rng.calls - before).toBeGreaterThan(1);
  });

  it('考え直す間隔は、強さの秒数に揺らぎを掛けてから tick に切り上げる', () => {
    // 原型は、揺らぎを掛けた秒数から 1/60 秒ずつ引き、0 以下になったフレームで考え直す。
    const intervals = [1, 2, 3, 4, 5, 6, 7, 8].map((seed) => {
      const scene = duel('rabbit', { col: 9, row: 7 }, { col: 19, row: 13 }, 'normal');
      const source = new CpuInputSource(0, CPU_LEVELS.normal, seed);
      source.next(scene.world);
      const exact = 0.26 * (1 + source.memory.jitter) * 60;
      return { got: source.memory.thinkIn, exact };
    });
    expect(intervals.map((i) => i.got)).toEqual(intervals.map((i) => Math.ceil(i.exact)));
    // 四捨五入と答えが分かれる揺らぎを含んでいること（含まなければ、この確認は切り上げを見分けられない）。
    expect(intervals.some((i) => Math.round(i.exact) !== Math.ceil(i.exact))).toBe(true);
  });
});
