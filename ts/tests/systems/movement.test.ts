import { describe, expect, it } from 'vitest';

import { abilityOf } from '../../src/domain/abilities/registry.js';
import { tick, TICKS_PER_SECOND } from '../../src/domain/core/Tick.js';
import { collides } from '../../src/domain/systems/MovementSystem.js';
import { MAX_SHOES, MAX_SPEED, PLAYER_RADIUS } from '../../src/domain/rules/tuning.js';
import { OUT } from '../../src/domain/state/Life.js';
import { speedOf } from '../../src/domain/state/PlayerState.js';
import { advance, makeWorld, onlyFor, press } from '../helpers.js';

describe('移動', () => {
  it('押した向きへ進む', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    const before = player.position.x;
    advance(world, onlyFor(world, 0, press({ right: true })), 30);
    expect(player.position.x).toBeGreaterThan(before);
  });

  it('押していなければ動かない', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    const before = { ...player.position };
    advance(world, onlyFor(world, 0, press({})), 60);
    expect(player.position).toEqual(before);
  });

  it('壁の向こうへは出られない', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    // 開始位置は (1,1)。左と上はどちらも外周の壁。
    advance(world, onlyFor(world, 0, press({ left: true })), 600);
    expect(player.position.x - PLAYER_RADIUS).toBeGreaterThanOrEqual(1);
  });

  it('いちばん速い状態でも壁をすり抜けない', () => {
    // 1 tick の移動距離が伸びると、当たり判定を挟まずに薄い壁を
    // 通り抜けることがある。移動を細かく分けているのはそのため。
    const world = makeWorld();
    const player = world.players[0]!;
    player.shoes = MAX_SHOES;
    advance(world, onlyFor(world, 0, press({ up: true })), 600);
    expect(player.position.y - PLAYER_RADIUS).toBeGreaterThanOrEqual(1);
  });

  it('向きが操作に追従する', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    advance(world, onlyFor(world, 0, press({ right: true })), 1);
    expect(player.facing).toBe('right');
    advance(world, onlyFor(world, 0, press({ down: true })), 1);
    expect(player.facing).toBe('down');
  });

  it('斜めに押すと横だけ動く', () => {
    // 斜め移動を許すと、格子状の通路では壁沿いに滑る動きになり、
    // 曲がり角の駆け引きが消える。1軸に丸めている。
    const world = makeWorld();
    const player = world.players[0]!;
    const before = { ...player.position };
    advance(world, onlyFor(world, 0, press({ right: true, down: true })), 20);
    expect(player.position.x).toBeGreaterThan(before.x);
    expect(player.position.y).toBe(before.y);
  });

  it('曲がり角で通路の中央へ寄る', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    // わざと通路の中央からずらす。
    player.position = { x: player.position.x, y: player.position.y + 0.2 };
    advance(world, onlyFor(world, 0, press({ right: true })), 30);
    // 中央（整数 + 0.5）へ近づいている。
    const distanceToCenter = Math.abs(player.position.y - (Math.floor(player.position.y) + 0.5));
    expect(distanceToCenter).toBeLessThan(0.2);
  });

  it('靴を取ると速くなる', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    const base = speedOf(player);
    player.shoes = 3;
    expect(speedOf(player)).toBeGreaterThan(base);
  });

  it('靴を上限まで取っても、速度の上限には届かない', () => {
    // 速度の上限（9.4 マス/秒）は、靴を取りきった状態（9.16 マス/秒）の
    // 少し上に置いてある。取りきった時点で頭打ちになると、
    // 最後の1個を取った手応えが無くなる。
    const world = makeWorld();
    const player = world.players[0]!;
    player.shoes = MAX_SHOES;
    expect(speedOf(player)).toBeLessThan(MAX_SPEED);
  });

  it('それでも速度には上限がある', () => {
    // 靴の段数はアイテムを取る側で上限を守るが、速度の計算自体も
    // 頭打ちにしておく。ここが伸び続けると、1 tick の移動距離が
    // 壁の厚みを超えてすり抜ける。
    const world = makeWorld();
    const player = world.players[0]!;
    player.shoes = 9999;
    expect(speedOf(player)).toBe(MAX_SPEED);
  });

  /*
   * 以下の速さの期待値は、原型（legacy/animal-bomber.html の getSpeed）を画面なしで動かして
   * 測った値（マス/秒）。この版は 1 tick あたりで持つので、60 を掛けて比べる。
   */
  const perSecond = (perTick: number): number => perTick * TICKS_PER_SECOND;

  it('上限で止めるのは最後（靴で上限を超える動物が「超スロー」を踏んだとき、先に止めない）', () => {
    const world = makeWorld(1234, ['rabbit', 'fox']);
    const rabbit = world.players[0]!;
    const multiplier = abilityOf('rabbit').speedMultiplier;
    const measured: Record<number, [number, number]> = {
      10: [8.714, 3.65988],
      11: [9.134, 3.83628],
      12: [9.4, 4.01268],
      13: [9.4, 4.18908],
    };
    for (const [shoes, [plain, slow]] of Object.entries(measured)) {
      rabbit.shoes = Number(shoes);
      rabbit.effects.clear('slow');
      expect(perSecond(speedOf(rabbit, multiplier)), `靴 ${shoes}`).toBeCloseTo(plain, 5);
      rabbit.effects.add('slow', tick(100), tick(100));
      expect(perSecond(speedOf(rabbit, multiplier)), `靴 ${shoes}・超スロー`).toBeCloseTo(slow, 5);
    }
  });

  it('壊せるブロックの中では、足の速さと靴のぶんの 0.18 倍。超スローは適用され、とまれないは適用されず、下限は 0.42', () => {
    const world = makeWorld(1234, ['mole', 'fox']);
    const mole = world.players[0]!;
    const multiplier = abilityOf('mole').speedMultiplier;
    const speed = (shoes: number, effects: readonly ('slow' | 'runaway')[], tile: 'empty' | 'soft'): number => {
      mole.shoes = shoes;
      mole.effects.clear('slow');
      mole.effects.clear('runaway');
      for (const effect of effects) mole.effects.add(effect, tick(100), tick(100));
      return perSecond(speedOf(mole, multiplier, tile));
    };
    expect(speed(0, [], 'empty')).toBeCloseTo(3.33, 5);
    expect(speed(0, ['runaway'], 'empty')).toBeCloseTo(8.648, 5);
    expect(speed(0, [], 'soft')).toBeCloseTo(0.5994, 5);
    expect(speed(5, [], 'soft')).toBeCloseTo(0.9774, 5);
    expect(speed(0, ['slow'], 'soft')).toBeCloseTo(0.42, 5);
    expect(speed(0, ['runaway'], 'soft')).toBeCloseTo(0.5994, 5);
    expect(speed(13, ['slow'], 'soft')).toBeCloseTo(0.664524, 5);
  });

  it('ブロックの中へ入ると、体の中心が入った次の tick から遅くなる', () => {
    // (3,7) の中央から右へ。(4,7) と (5,7) は壊せるブロック。中心が (4,7) に入るのは 10 tick 目。
    const world = makeWorld(5, ['mole', 'frog']);
    const mole = world.players[0]!;
    for (const { cell, tile } of world.board.cells()) if (tile === 'soft') world.board.set(cell, 'empty');
    world.board.set({ col: 4, row: 7 }, 'soft');
    world.board.set({ col: 5, row: 7 }, 'soft');
    mole.position = { x: 3.5, y: 7.5 };
    world.players[1]!.position = { x: 19.5, y: 13.5 };
    const xs: number[] = [];
    for (let t = 1; t <= 60; t += 1) {
      advance(world, onlyFor(world, 0, press({ right: true })), 1);
      if (t % 10 === 0) xs.push(mole.position.x);
    }
    [4.055, 4.1549, 4.2548, 4.3547, 4.4546, 4.5545].forEach((x, i) => expect(xs[i]).toBeCloseTo(x, 5));
  });

  it('倒れているプレイヤーは動かない', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    player.life = OUT;
    const before = { ...player.position };
    advance(world, onlyFor(world, 0, press({ right: true })), 60);
    expect(player.position).toEqual(before);
  });
});

describe('当たり判定', () => {
  it('いま重なっているマスは移動先の判定から外す', () => {
    // 足元のマスが後から壁になっても閉じ込められないようにするため。
    const world = makeWorld();
    world.board.set({ col: 3, row: 3 }, 'soft');
    const player = world.players[0]!;
    const inside = { x: 3.5, y: 3.5 };
    // 壁の中から、同じ壁の中へわずかに動く分には止まらない。
    expect(collides(world, player, inside, { x: 3.52, y: 3.5 })).toBe(false);
  });

  it('外へ出たあとは、その壁へ戻れない', () => {
    const world = makeWorld();
    world.board.set({ col: 3, row: 3 }, 'soft');
    const player = world.players[0]!;
    const outside = { x: 4.5, y: 3.5 };
    expect(collides(world, player, outside, { x: 3.9, y: 3.5 })).toBe(true);
  });

  it('盤面の外は壁として扱う', () => {
    const world = makeWorld();
    expect(world.board.at({ col: -1, row: 0 })).toBe('hard');
    expect(world.board.at({ col: 0, row: -5 })).toBe('hard');
    expect(world.board.isBlocked({ col: 999, row: 999 })).toBe(true);
  });
});
