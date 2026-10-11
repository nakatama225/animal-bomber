import { describe, expect, it } from 'vitest';

import { centerOf, type Cell } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { placeBombAt } from '../../src/domain/mutations/bombs.js';
import type { PlayerState } from '../../src/domain/state/PlayerState.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { clearBoard, makeWorld, onlyFor, press, sameForAll } from '../helpers.js';

/*
 * ぞうの通常技（鼻水噴射）を、原型（legacy/animal-bomber.html の elephantSnot）に合わせる。
 * 期待値は原型を画面なしで動かして測った値。原型は技のボタンを押した瞬間に吹くので、そのフレームを 0 と数えた。
 * この版は離した tick に吹くので、その tick を 0 と数える。
 */

/** 悪いアイテムのうんこの抽選でかかりうる状態。 */
const POOP_EFFECTS = ['reverse', 'nobomb', 'runaway', 'weak', 'autobomb', 'slow'] as const;

function arena(): { world: WorldState; elephant: PlayerState; rabbit: PlayerState; sim: Simulation } {
  const world = makeWorld(5, ['elephant', 'rabbit']);
  clearBoard(world);
  world.items = [];
  const [elephant, rabbit] = world.players as [PlayerState, PlayerState];
  elephant.position = centerOf({ col: 3, row: 7 });
  elephant.facing = 'right';
  rabbit.position = centerOf({ col: 19, row: 13 });
  rabbit.maxBombs = 5;
  return { world, elephant, rabbit, sim: new Simulation() };
}

/** 0番に技のボタンを押して離させる。吹いた tick（離した tick）のイベントを返す。 */
function snot(world: WorldState, sim: Simulation): SimEvent[] {
  sim.step(world, sameForAll(world, press({})));
  sim.step(world, onlyFor(world, 0, press({ action: true })));
  return sim.step(world, sameForAll(world, press({})));
}

function bombAt(world: WorldState, owner: PlayerState, cell: Cell): void {
  placeBombAt(world, owner, cell)!.fuse = tick(999);
}

const bombCells = (world: WorldState): string[] => world.bombs.map((bomb) => `${bomb.cell.col},${bomb.cell.row}`);
const itemCells = (world: WorldState): string[] =>
  world.items.map((item) => `${item.kind}${item.scatteredBy !== undefined ? '(撒いた)' : ''}@${item.cell.col},${item.cell.row}`);

describe('鼻水噴射（原型 elephantSnot）', () => {
  it('正面2マスの爆弾の火を消し（爆弾ごと消える）、置いたプレイヤーの手持ちが戻る。3マス先には届かない', () => {
    const { world, rabbit, sim } = arena();
    for (const col of [4, 5, 6]) bombAt(world, rabbit, { col, row: 7 });
    expect(rabbit.activeBombs).toBe(3);
    const events = snot(world, sim);
    expect(bombCells(world)).toEqual(['6,7']);
    expect(rabbit.activeBombs).toBe(1);
    expect(events.filter((event) => event.type === 'bombDoused')).toHaveLength(2);
  });

  it('ふつうのうんこは流され、吹いた tick から 27 tick 目に消える。撒かれたうんこは流せない', () => {
    const { world, rabbit, sim } = arena();
    world.items.push({ id: world.ids.take(), cell: { col: 4, row: 7 }, kind: 'poop' });
    world.items.push({ id: world.ids.take(), cell: { col: 5, row: 7 }, kind: 'poop', scatteredBy: rabbit.id, expiresAt: tick(9999) });
    snot(world, sim);
    expect(world.items.find((item) => item.cell.col === 4)?.meltingUntil).toBeDefined();
    expect(world.items.find((item) => item.cell.col === 5)?.meltingUntil).toBeUndefined();
    let goneAt: number | null = null;
    for (let t = 1; t <= 60 && goneAt === null; t += 1) {
      const events = sim.step(world, sameForAll(world, press({})));
      if (!world.items.some((item) => item.cell.col === 4)) {
        goneAt = t;
        expect(events).toContainEqual({ type: 'itemWashed', cell: { col: 4, row: 7 }, kind: 'poop' });
      }
    }
    expect(goneAt).toBe(27);
    expect(itemCells(world)).toEqual(['poop(撒いた)@5,7']);
  });

  it('溶けている間のうんこは、踏んでも効かない', () => {
    const { world, rabbit, sim } = arena();
    world.items.push({ id: world.ids.take(), cell: { col: 4, row: 7 }, kind: 'poop' });
    snot(world, sim);
    rabbit.position = centerOf({ col: 4, row: 7 });
    sim.step(world, sameForAll(world, press({})));
    expect(POOP_EFFECTS.filter((kind) => rabbit.effects.has(kind))).toEqual([]);
    expect(itemCells(world)).toEqual(['poop@4,7']);
  });

  it('柱の向こうへは届かない', () => {
    // (3,6) から右へ。1マス目の (4,6) が柱で、2マス目の (5,6) の爆弾は残る（原型の答え）。
    const { world, elephant, rabbit, sim } = arena();
    elephant.position = centerOf({ col: 3, row: 6 });
    expect(world.board.at({ col: 4, row: 6 })).toBe('hard');
    bombAt(world, rabbit, { col: 5, row: 6 });
    snot(world, sim);
    expect(bombCells(world)).toEqual(['5,6']);
  });

  it('壊せるブロックのマスまでは届き、その先へは届かない', () => {
    const { world, sim } = arena();
    world.board.set({ col: 4, row: 7 }, 'soft');
    world.items.push({ id: world.ids.take(), cell: { col: 5, row: 7 }, kind: 'poop' });
    snot(world, sim);
    expect(world.items[0]?.meltingUntil).toBeUndefined();
    expect(world.board.at({ col: 4, row: 7 })).toBe('soft');
  });

  it('5 秒に1回（何も消せなくても間隔は始まる）', () => {
    const { world, rabbit, sim } = arena();
    snot(world, sim);
    bombAt(world, rabbit, { col: 4, row: 7 });
    snot(world, sim);
    expect(bombCells(world)).toEqual(['4,7']);
    // 最初に吹いてから 300 tick たてば、また吹ける。
    for (let t = 0; t < 300; t += 1) sim.step(world, sameForAll(world, press({})));
    snot(world, sim);
    expect(bombCells(world)).toEqual([]);
  });
});
