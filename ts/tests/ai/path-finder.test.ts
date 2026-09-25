import { describe, expect, it } from 'vitest';

import { abilityOf } from '../../src/domain/abilities/registry.js';
import { sameCell, type Cell } from '../../src/domain/core/Coord.js';
import { addBlast } from '../../src/domain/mutations/explode.js';
import { DangerMap } from '../../src/domain/query/DangerMap.js';
import { findPath } from '../../src/domain/query/PathFinder.js';
import { clearBoard, makeWorld } from '../helpers.js';


const START: Cell = { col: 1, row: 1 };
const at = (target: Cell) => (cell: Cell) => sameCell(cell, target);

describe('経路の探索', () => {
  it('最短の経路を、出発点の次のマスから目的地まで返す', () => {
    const world = makeWorld();
    clearBoard(world);
    const path = findPath(world, world.players[0]!, START, at({ col: 5, row: 1 }), {
      maxDistance: 20,
    });
    expect(path).toEqual([
      { col: 2, row: 1 },
      { col: 3, row: 1 },
      { col: 4, row: 1 },
      { col: 5, row: 1 },
    ]);
  });

  it('燃えているマスを避けて回り道する', () => {
    const world = makeWorld();
    clearBoard(world);
    addBlast(world, { col: 3, row: 1 }, 1, true);
    const path = findPath(world, world.players[0]!, START, at({ col: 5, row: 1 }), {
      maxDistance: 20,
      danger: DangerMap.of(world),
      avoidWithin: 0,
    });
    expect(path).not.toBeNull();
    expect(path!.some((cell) => sameCell(cell, { col: 3, row: 1 }))).toBe(false);
    expect(path!.at(-1)).toEqual({ col: 5, row: 1 });
  });

  it('これから置く爆弾のマスは塞がれたものとして扱う', () => {
    const world = makeWorld();
    clearBoard(world);
    const path = findPath(world, world.players[0]!, START, at({ col: 3, row: 1 }), {
      maxDistance: 20,
      extraObstacles: [{ col: 2, row: 1 }],
    });
    expect(path!.some((cell) => sameCell(cell, { col: 2, row: 1 }))).toBe(false);
  });

  it('踏むと損をするアイテムを避けられる', () => {
    const world = makeWorld();
    clearBoard(world);
    world.items.push({ id: world.ids.take(), cell: { col: 2, row: 1 }, kind: 'banana' });
    const path = findPath(world, world.players[0]!, START, at({ col: 3, row: 1 }), {
      maxDistance: 20,
      avoidHarmfulItems: true,
    });
    expect(path!.some((cell) => sameCell(cell, { col: 2, row: 1 }))).toBe(false);
  });

  it('壊せるブロックを抜けられる動物は、その判定を渡すと抜ける', () => {
    const world = makeWorld(1234, ['mole', 'rabbit']);
    clearBoard(world);
    world.board.set({ col: 2, row: 1 }, 'soft');
    const mole = world.players[0]!;
    const goal = at({ col: 3, row: 1 });

    // 判定を渡さなければ、ブロックの向こうへは2歩では届かない。
    expect(findPath(world, mole, START, goal, { maxDistance: 2 })).toBeNull();

    const passesThrough = abilityOf('mole').passesThrough!.bind(abilityOf('mole'));
    expect(findPath(world, mole, START, goal, { maxDistance: 2, passesThrough })).toEqual([
      { col: 2, row: 1 },
      { col: 3, row: 1 },
    ]);
  });

  it('届かなければ null', () => {
    const world = makeWorld();
    clearBoard(world);
    const path = findPath(world, world.players[0]!, START, at({ col: 21, row: 15 }), {
      maxDistance: 3,
    });
    expect(path).toBeNull();
  });
});
