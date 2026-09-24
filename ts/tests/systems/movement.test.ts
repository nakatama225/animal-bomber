import { describe, expect, it } from 'vitest';

import { collides } from '../../src/domain/systems/MovementSystem.js';
import { MAX_SHOES, MAX_SPEED, PLAYER_RADIUS } from '../../src/domain/rules/tuning.js';
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

  it('倒れているプレイヤーは動かない', () => {
    const world = makeWorld();
    const player = world.players[0]!;
    player.life = 'dead';
    const before = { ...player.position };
    advance(world, onlyFor(world, 0, press({ right: true })), 60);
    expect(player.position).toEqual(before);
  });
});

describe('当たり判定', () => {
  it('いま重なっているマスは移動先の判定から外す', () => {
    // 足元のマスが後から壁になっても閉じ込められないようにするため。
    const world = makeWorld();
    const board = world.board;
    board.set({ col: 3, row: 3 }, 'soft');
    const inside = { x: 3.5, y: 3.5 };
    // 壁の中から、同じ壁の中へわずかに動く分には止まらない。
    expect(collides(board, inside, { x: 3.52, y: 3.5 })).toBe(false);
  });

  it('外へ出たあとは、その壁へ戻れない', () => {
    const world = makeWorld();
    const board = world.board;
    board.set({ col: 3, row: 3 }, 'soft');
    const outside = { x: 4.5, y: 3.5 };
    expect(collides(board, outside, { x: 3.9, y: 3.5 })).toBe(true);
  });

  it('盤面の外は壁として扱う', () => {
    const world = makeWorld();
    expect(world.board.at({ col: -1, row: 0 })).toBe('hard');
    expect(world.board.at({ col: 0, row: -5 })).toBe('hard');
    expect(world.board.isBlocked({ col: 999, row: 999 })).toBe(true);
  });
});
