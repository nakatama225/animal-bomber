import { describe, expect, it } from 'vitest';

import { SlimeBombActor } from '../../src/domain/abilities/frog/SlimeBombActor.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
import { centerOf, type Cell } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { placeBombAt } from '../../src/domain/mutations/bombs.js';
import { OUT } from '../../src/domain/state/Life.js';
import type { PlayerState } from '../../src/domain/state/PlayerState.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { clearBoard, makeWorld, onlyFor, press, sameForAll } from '../helpers.js';

/*
 * かえるの粘膜爆弾と舌を、原型（legacy/animal-bomber.html の slimeBurst・updateSlimes・updateTongue）に
 * 合わせる。期待値は原型を画面なしで動かして測った値。
 *
 * ⚠️ 跳ぶ向きは、この版は縦横の4方向（原型は斜めも入れた8方向）。この違いは今回の直しに含めていない。
 */

/** 跳ねる間隔。SlimeBombActor の HOP_INTERVAL と同じ。 */
const HOP_INTERVAL = 21;

function arena(seed = 2468): { world: WorldState; frog: PlayerState; rabbit: PlayerState } {
  const world = makeWorld(seed, ['frog', 'rabbit']);
  clearBoard(world);
  world.items = [];
  const [frog, rabbit] = world.players as [PlayerState, PlayerState];
  frog.position = centerOf({ col: 1, row: 13 });
  rabbit.position = centerOf({ col: 19, row: 1 });
  return { world, frog, rabbit };
}

/** 粘膜爆弾の actor だけを進める（ほかの System を通さない）。 */
function runActor(world: WorldState, actor: SlimeBombActor, ticks: number): SimEvent[] {
  const events: SimEvent[] = [];
  for (let i = 0; i < ticks; i += 1) events.push(...actor.tick(world).events);
  return events;
}

const blastCells = (world: WorldState): string[] =>
  world.blasts.map((blast) => `${blast.cell.col},${blast.cell.row}${blast.isCenter ? 'C' : ''}`);

function bombWithLongFuse(world: WorldState, owner: PlayerState, cell: Cell): void {
  owner.maxBombs = 9;
  const bomb = placeBombAt(world, owner, cell);
  if (bomb === undefined) throw new Error('爆弾を置けなかった');
  bomb.fuse = tick(9999);
}

describe('粘膜爆弾が跳ね終わったとき（原型 slimeBurst）', () => {
  it('手持ちを出し切っていても爆発する', () => {
    const { world, frog } = arena();
    frog.activeBombs = frog.maxBombs;
    const events = runActor(world, new SlimeBombActor({ col: 6, row: 7 }, frog, 0), HOP_INTERVAL);
    expect(events.some((e) => e.type === 'exploded')).toBe(true);
    expect(blastCells(world)).toEqual(['6,7C', '7,7', '5,7']);
  });

  it('柱の上で跳ね終わったら、隣の空きマスへずれて爆発する（原型の順で最初は右）', () => {
    const { world, frog } = arena();
    runActor(world, new SlimeBombActor({ col: 8, row: 8 }, frog, 0), HOP_INTERVAL);
    expect(blastCells(world)).toEqual(['9,8C', '9,9', '9,7']);
  });

  it('壊せるブロックの上なら、隣へずれて爆発し、そのブロックは爆風で壊れる', () => {
    const { world, frog } = arena();
    world.board.set({ col: 6, row: 7 }, 'soft');
    runActor(world, new SlimeBombActor({ col: 6, row: 7 }, frog, 0), HOP_INTERVAL);
    expect(blastCells(world)[0]).toBe('7,7C');
    expect(world.board.at({ col: 6, row: 7 })).toBe('empty');
  });

  it('爆弾の上なら、隣へずれて爆発し、その爆弾も誘爆する', () => {
    const { world, frog, rabbit } = arena();
    bombWithLongFuse(world, rabbit, { col: 6, row: 7 });
    runActor(world, new SlimeBombActor({ col: 6, row: 7 }, frog, 0), HOP_INTERVAL);
    const centers = blastCells(world).filter((cell) => cell.endsWith('C'));
    expect(centers).toEqual(['7,7C', '6,7C']);
    expect(world.bombs).toEqual([]);
  });

  it('まわりの8マスがどこも降りられなければ、その場で中心の爆風だけを出す', () => {
    const { world, frog } = arena();
    const around: Cell[] = [
      [1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1],
    ].map(([dx, dy]) => ({ col: 8 + dx!, row: 8 + dy! }));
    for (const cell of around) world.board.set(cell, 'soft');
    const events = runActor(world, new SlimeBombActor({ col: 8, row: 8 }, frog, 0), HOP_INTERVAL);
    expect(blastCells(world)).toEqual(['8,8C']);
    expect(around.every((cell) => world.board.at(cell) === 'soft')).toBe(true);
    expect(world.bombs).toEqual([]);
    expect(events.filter((e) => e.type === 'exploded')).toHaveLength(1);
  });

  it('本物の爆弾を出したままでも爆発し、その爆弾は残る（手持ちの数も変わらない）', () => {
    // ⚠️ 原型は手持ちの数を1つ多く減らす（生やして1減らし、爆発でもう1減らす）。原型の注記
    // 「手持ちは減らさない」の意図に合わせ、この版は差し引きで変えない。
    const { world, frog } = arena();
    bombWithLongFuse(world, frog, { col: 3, row: 13 });
    const before = frog.activeBombs;
    runActor(world, new SlimeBombActor({ col: 6, row: 7 }, frog, 0), HOP_INTERVAL);
    expect(blastCells(world)[0]).toBe('6,7C');
    expect(world.bombs.map((bomb) => `${bomb.cell.col},${bomb.cell.row}`)).toEqual(['3,13']);
    expect(frog.activeBombs).toBe(before);
  });
});

describe('粘膜爆弾の跳ぶ先（原型 updateSlimes）', () => {
  /** 跳ねる回数5の粘膜爆弾を1回跳ばし、着地したマスと残りの回数を返す。 */
  function hopOnce(seed: number, from: Cell, setup: (world: WorldState, rabbit: PlayerState) => void = () => {}) {
    const { world, frog, rabbit } = arena(seed);
    setup(world, rabbit);
    const actor = new SlimeBombActor(from, frog, 5);
    runActor(world, actor, HOP_INTERVAL);
    return { cell: `${actor.cell.col},${actor.cell.row}`, hopsLeft: actor.hopsLeft };
  }

  it('外周（葱ボンの通り道）には乗らない', () => {
    const landed = new Set<string>();
    for (let seed = 1; seed <= 200; seed += 1) landed.add(hopOnce(seed, { col: 2, row: 3 }).cell);
    expect([...landed].sort()).toEqual(['2,1', '2,5', '4,3']);
  });

  it('爆弾のあるマスには乗らない', () => {
    const landed = new Set<string>();
    for (let seed = 1; seed <= 200; seed += 1) {
      landed.add(
        hopOnce(seed, { col: 1, row: 1 }, (world, rabbit) => bombWithLongFuse(world, rabbit, { col: 3, row: 1 })).cell,
      );
    }
    expect([...landed]).toEqual(['1,3']);
  });

  it('どこにも跳べなければその場に留まり、跳ねる回数は減る', () => {
    for (let seed = 1; seed <= 50; seed += 1) {
      const result = hopOnce(seed, { col: 1, row: 1 }, (world, rabbit) => {
        bombWithLongFuse(world, rabbit, { col: 3, row: 1 });
        bombWithLongFuse(world, rabbit, { col: 1, row: 3 });
      });
      expect(result).toEqual({ cell: '1,1', hopsLeft: 4 });
    }
  });

  it('ラウンドの始まりの盤面で開始位置から投げても、どの種でも跳ね終わると爆発する', () => {
    const misfired: number[] = [];
    for (let seed = 1; seed <= 200; seed += 1) {
      const world = makeWorld(seed, ['frog', 'rabbit']);
      const frog = world.players[0]!;
      frog.specialCharges = 1;
      const sim = new Simulation();
      sim.step(world, sameForAll(world, press({})));
      for (let i = 0; i < abilityOf('frog').holdTicks; i += 1) {
        sim.step(world, onlyFor(world, 0, press({ action: true })));
      }
      let exploded = false;
      for (let i = 0; i < 400 && !exploded; i += 1) {
        const events = sim.step(world, sameForAll(world, press({})));
        exploded = events.some((e) => e.type === 'exploded' && e.owner === frog.id);
      }
      if (!exploded) misfired.push(seed);
    }
    expect(misfired).toEqual([]);
  });
});

describe('舌が止まるもの（原型 updateTongue）', () => {
  /** かえるを (3,5) 右向きに置き、火を itemCol に置いて、舌を1回出す。 */
  function tongue(blocker: 'none' | 'bomb' | 'player' | 'playerOut', itemCol: number) {
    const world = makeWorld(2468, ['frog', 'rabbit']);
    clearBoard(world);
    world.items = [];
    const [frog, rabbit] = world.players as [PlayerState, PlayerState];
    frog.position = centerOf({ col: 3, row: 5 });
    frog.facing = 'right';
    rabbit.position = centerOf({ col: 19, row: 13 });
    world.items.push({ id: world.ids.take(), cell: { col: itemCol, row: 5 }, kind: 'fire' });
    if (blocker === 'bomb') bombWithLongFuse(world, rabbit, { col: 5, row: 5 });
    if (blocker === 'player' || blocker === 'playerOut') rabbit.position = centerOf({ col: 5, row: 5 });
    if (blocker === 'playerOut') rabbit.life = OUT;
    const power = frog.power;
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    sim.step(world, onlyFor(world, 0, press({ action: true })));
    for (let i = 0; i < 80; i += 1) sim.step(world, sameForAll(world, press({})));
    return {
      gained: frog.power - power,
      items: world.items.map((item) => `${item.kind}@${item.cell.col},${item.cell.row}`),
      action: frog.action,
    };
  }

  it('爆弾の向こうのアイテムは取らない（舌は爆弾で止まる）', () => {
    expect(tongue('bomb', 7)).toMatchObject({ gained: 0, items: ['fire@7,5'], action: null });
  });

  it('盤面の上のほかのプレイヤーの向こうのアイテムは取らない', () => {
    expect(tongue('player', 7)).toMatchObject({ gained: 0, items: ['fire@7,5'], action: null });
  });

  it('対照：何も無ければ取る（かえるは効果が2倍）', () => {
    expect(tongue('none', 7)).toMatchObject({ gained: 2, items: [] });
  });

  it('対照：退場したプレイヤーでは止まらない', () => {
    expect(tongue('playerOut', 7)).toMatchObject({ gained: 2, items: [] });
  });

  it('対照：爆弾やプレイヤーの手前のアイテムは取る', () => {
    expect(tongue('bomb', 4)).toMatchObject({ gained: 2, items: [] });
    expect(tongue('player', 4)).toMatchObject({ gained: 2, items: [] });
  });
});
