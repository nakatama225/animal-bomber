import { describe, expect, it } from 'vitest';

import { abilityOf } from '../../src/domain/abilities/registry.js';
import { centerOf } from '../../src/domain/core/Coord.js';
import { placeBomb } from '../../src/domain/mutations/bombs.js';
import { hurt } from '../../src/domain/mutations/damage.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { advance, makeWorld, onlyFor, press } from '../helpers.js';

const ELEPHANT_HOLD = abilityOf('elephant').holdTicks;

/** ぞうを席0に置いた世界。 */
function elephantWorld(): ReturnType<typeof makeWorld> {
  return makeWorld(31337, ['elephant', 'rabbit']);
}

/** 技のボタンを押し続けて、とくぎを出す。 */
function triggerCharge(
  world: ReturnType<typeof makeWorld>,
  sim = new Simulation(),
): void {
  const player = world.players[0]!;
  player.specialCharges = 1;
  // ラウンド開始時のロックを外すため、まず1 tick 離す。
  sim.step(world, onlyFor(world, 0, press({})));
  for (let i = 0; i < ELEPHANT_HOLD; i += 1) {
    sim.step(world, onlyFor(world, 0, press({ action: true })));
  }
}

describe('とくぎの出し方', () => {
  it('長押しでとくぎが始まる', () => {
    const world = elephantWorld();
    triggerCharge(world);
    expect(world.players[0]!.action?.kind).toBe('charge');
  });

  it('溜めが無ければ出ない', () => {
    // とくぎはチキンを拾って溜めた回数ぶんだけ使える。
    const world = elephantWorld();
    const sim = new Simulation();
    sim.step(world, onlyFor(world, 0, press({})));
    for (let i = 0; i < ELEPHANT_HOLD + 10; i += 1) {
      sim.step(world, onlyFor(world, 0, press({ action: true })));
    }
    expect(world.players[0]!.action).toBeNull();
  });

  it('溜めを1つ使う', () => {
    const world = elephantWorld();
    world.players[0]!.specialCharges = 2;
    const sim = new Simulation();
    sim.step(world, onlyFor(world, 0, press({})));
    for (let i = 0; i < ELEPHANT_HOLD; i += 1) {
      sim.step(world, onlyFor(world, 0, press({ action: true })));
    }
    expect(world.players[0]!.specialCharges).toBe(1);
  });

  it('ラウンド開始時から押していると、離すまで出ない', () => {
    // キーボードでは文字入力の繰り返し遅延が緩衝材になっていたが、
    // ゲームパッドは次の tick で押下が戻るため、これが無いと
    // 開始 0.5 秒でとくぎが暴発する。
    const world = elephantWorld();
    world.players[0]!.specialCharges = 1;
    const sim = new Simulation();
    for (let i = 0; i < ELEPHANT_HOLD + 30; i += 1) {
      sim.step(world, onlyFor(world, 0, press({ action: true })));
    }
    expect(world.players[0]!.action).toBeNull();
  });
});

describe('突進', () => {
  it('操作を受け付けない', () => {
    const world = elephantWorld();
    const player = world.players[0]!;
    player.facing = 'right';
    triggerCharge(world);
    const before = { ...player.position };
    // 逆向きを押しても、突進の向きへ進む。
    advance(world, onlyFor(world, 0, press({ left: true })), 5);
    expect(player.position.x).toBeGreaterThan(before.x);
  });

  it('壊せるブロックを踏み潰して進む', () => {
    const world = elephantWorld();
    const player = world.players[0]!;
    player.position = centerOf({ col: 1, row: 3 });
    player.facing = 'right';
    world.board.set({ col: 3, row: 3 }, 'soft');
    triggerCharge(world);
    advance(world, onlyFor(world, 0, press({})), 60);
    expect(world.board.at({ col: 3, row: 3 })).toBe('empty');
  });

  it('柱に当たると止まる', () => {
    const world = elephantWorld();
    const player = world.players[0]!;
    player.position = centerOf({ col: 1, row: 3 });
    player.facing = 'up'; // (1,2) は通路、(1,1) も通路、(1,0) が外周の壁
    triggerCharge(world);
    advance(world, onlyFor(world, 0, press({})), 120);
    expect(player.action).toBeNull();
    expect(player.position.y).toBeGreaterThan(1);
  });

  it('爆弾に突っ込むと起爆させ、自分は止まらない', () => {
    const world = elephantWorld();
    const player = world.players[0]!;
    const other = world.players[1]!;
    player.position = centerOf({ col: 1, row: 3 });
    player.facing = 'right';
    other.position = centerOf({ col: 5, row: 3 });
    for (const col of [2, 3, 4, 5, 6, 7]) world.board.set({ col, row: 3 }, 'empty');
    placeBomb(world, other);
    triggerCharge(world);
    const beforeX = player.position.x;
    advance(world, onlyFor(world, 0, press({})), 30);
    expect(world.bombs).toHaveLength(0); // 起爆した
    expect(player.position.x).toBeGreaterThan(beforeX); // 止まっていない
  });
});

describe('突進中の被弾', () => {
  it('受けるダメージが減るが、0 にはならない', () => {
    // 無敵にすると、突進を撃ち続けるだけで勝ててしまう。
    // 「止まらないが痛い」が突進の設計。
    const world = elephantWorld();
    const player = world.players[0]!;
    triggerCharge(world);
    const before = player.hp;
    hurt(world, player, 1, 2);
    const damage = before - player.hp;
    expect(damage).toBeGreaterThan(0);
    expect(damage).toBeLessThan(2);
  });

  it('突進していなければ軽減されない', () => {
    // 前の確認が「常に減る」で通ってしまわないための対照。
    const world = elephantWorld();
    const player = world.players[0]!;
    const before = player.hp;
    hurt(world, player, 1, 2);
    expect(before - player.hp).toBe(2);
  });

  it('体当たりは当たらない状態になる', () => {
    const world = elephantWorld();
    triggerCharge(world);
    expect(world.players[0]!.action?.untouchable).toBe(true);
  });

  it('突進中は爆弾を置けない', () => {
    const world = elephantWorld();
    triggerCharge(world);
    const before = world.bombs.length;
    advance(world, onlyFor(world, 0, press({ bomb: true })), 3);
    expect(world.bombs.length).toBe(before);
  });
});

describe('突進と通り道のアイテム', () => {
  it('良いアイテムは吸い込む', () => {
    const world = elephantWorld();
    const player = world.players[0]!;
    player.position = centerOf({ col: 1, row: 3 });
    player.facing = 'right';
    for (const col of [2, 3, 4, 5]) world.board.set({ col, row: 3 }, 'empty');
    world.items.push({ id: world.ids.take(), cell: { col: 3, row: 3 }, kind: 'fire' });
    const before = player.power;
    triggerCharge(world);
    advance(world, onlyFor(world, 0, press({})), 30);
    expect(player.power).toBeGreaterThan(before);
  });

  it('悪いアイテムは抱えて運び、止まった所で撒く', () => {
    // 通り道のたまねぎ1つで突進が止まると、とくぎを使う判断そのものが
    // 成り立たなくなる。踏んでも効果を受けず、抱えて運ぶ。
    const world = elephantWorld();
    const player = world.players[0]!;
    player.position = centerOf({ col: 1, row: 3 });
    player.facing = 'right';
    for (const col of [2, 3, 4, 5]) world.board.set({ col, row: 3 }, 'empty');
    world.items.push({ id: world.ids.take(), cell: { col: 3, row: 3 }, kind: 'onion' });
    triggerCharge(world);
    advance(world, onlyFor(world, 0, press({})), 5);
    // 踏んでも泣いていない。
    expect(player.effects.has('stun')).toBe(false);
    advance(world, onlyFor(world, 0, press({})), 200);
    // 止まったあと、どこかに撒かれている。
    expect(world.items.some((item) => item.kind === 'onion')).toBe(true);
  });
});
