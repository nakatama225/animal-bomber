import { describe, expect, it } from 'vitest';

import { ChargeAction } from '../../src/domain/abilities/elephant/ChargeAction.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
import { cellOf, centerOf, sameCell, type Cell } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { placeBomb, placeBombAt } from '../../src/domain/mutations/bombs.js';
import { hurt } from '../../src/domain/mutations/damage.js';
import { itemEffectTicks, POOP_LIFETIME, type ItemKind } from '../../src/domain/rules/items.js';
import { isAlive, isBlastProof, isUntouchable, type PlayerState } from '../../src/domain/state/PlayerState.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { ItemSystem } from '../../src/domain/systems/ItemSystem.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { advance, clearBoard, grantSpecial, makeWorld, onlyFor, press, sameForAll } from '../helpers.js';

const ELEPHANT_HOLD = abilityOf('elephant').holdTicks;

/** プレイヤー0をぞうにした世界。 */
function elephantWorld(): ReturnType<typeof makeWorld> {
  return makeWorld(31337, ['elephant', 'rabbit']);
}

/** 技のボタンを押し続けて、とくぎを出す。 */
function triggerCharge(
  world: ReturnType<typeof makeWorld>,
  sim = new Simulation(),
): void {
  const player = world.players[0]!;
  grantSpecial(player, 1);
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
    grantSpecial(world.players[0]!, 2);
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
    grantSpecial(world.players[0]!, 1);
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

  it('葱は当たらない状態になるが、爆風・追いかける炎・体当たりの傷は当たる（原型の isUntouchable と isBlastProof）', () => {
    const world = elephantWorld();
    triggerCharge(world);
    const elephant = world.players[0]!;
    expect(isUntouchable(elephant)).toBe(true);
    expect(isBlastProof(elephant)).toBe(false);
  });

  it('突進中は爆弾を置けない', () => {
    const world = elephantWorld();
    triggerCharge(world);
    const before = world.bombs.length;
    advance(world, onlyFor(world, 0, press({ bomb: true })), 3);
    expect(world.bombs.length).toBe(before);
  });

  it('突進中は、勝手に設置の拍が来ても置かない（拍は進む）', () => {
    // 原型の canPlaceBomb は突進の最中を止め、勝手に設置もこの確かめを通る。
    const world = elephantWorld();
    const player = world.players[0]!;
    const sim = new Simulation();
    triggerCharge(world, sim);
    player.effects.add('autobomb', itemEffectTicks(4), itemEffectTicks(12));
    const before = world.bombs.length;
    advance(world, onlyFor(world, 0, press({})), 3, sim);
    // 突進が先に終わって置かなかっただけ、を除くため、まだ突進中であることも見る。
    expect(player.action?.kind).toBe('charge');
    expect(world.bombs.length).toBe(before);
    // 置けなかった拍も進むので、次の拍までの待ちが残っている。
    expect(player.autobombWait).toBeGreaterThan(0);
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

  it('撒いたうんこには、ふつうのうんこと同じ残る長さが付く（ほかの悪いアイテムには付かない）', () => {
    const world = elephantWorld();
    const player = world.players[0]!;
    clearBoard(world);
    world.items = [];
    player.position = centerOf({ col: 1, row: 3 });
    player.action = new ChargeAction('right');
    world.items.push({ id: world.ids.take(), cell: { col: 3, row: 3 }, kind: 'poop' });
    world.items.push({ id: world.ids.take(), cell: { col: 4, row: 3 }, kind: 'onion' });
    const sim = new Simulation();
    let spatAt = -1;
    for (let i = 0; i < 200 && spatAt < 0; i += 1) {
      const now = world.now;
      const events = sim.step(world, onlyFor(world, 0, press({})));
      if (events.some((e) => e.type === 'techniqueMoment' && e.moment === 'itemsSpat')) spatAt = now;
    }
    expect(spatAt).toBeGreaterThan(0);
    const expiry = Object.fromEntries(world.items.map((item) => [item.kind, item.expiresAt]));
    expect(expiry).toEqual({ poop: spatAt + POOP_LIFETIME, onion: undefined });
  });
});

/*
 * 以下は原型（legacy/animal-bomber.html の updateCharge・chargeSweep・destroySoft・update）に合わせた振る舞い。
 * 期待値は原型を画面なしで動かして測った値。突進は直に振る舞いを入れて始める（原型の elephantCharge と同じ時点）。
 */

/** 盤面を空にした世界。アイテムを片付け、開幕の無敵を外す。 */
function chargeArena(animals: [string, string], seed = 1234): WorldState {
  const world = makeWorld(seed, animals);
  clearBoard(world);
  world.items = [];
  for (const player of world.players) player.invulnerableUntil = tick(0);
  return world;
}

function putItem(world: WorldState, cell: Cell, kind: ItemKind): void {
  world.items.push({ id: world.ids.take(), cell, kind });
}

describe('突進で壊したブロックの抽選（原型 destroySoft）', () => {
  it('壊したブロックからも、ふつうの爆風と同じ割合でアイテムが出る（出るのは壊したマス）', () => {
    let broken = 0;
    let dropped = 0;
    for (let seed = 1; seed <= 200; seed += 1) {
      const world = chargeArena(['elephant', 'rabbit'], seed);
      const [elephant, rabbit] = world.players as [PlayerState, PlayerState];
      elephant.position = centerOf({ col: 1, row: 3 });
      rabbit.position = centerOf({ col: 19, row: 13 });
      world.board.set({ col: 3, row: 3 }, 'soft');
      elephant.action = new ChargeAction('right');
      const events: SimEvent[] = [];
      const sim = new Simulation();
      for (let i = 0; i < 10; i += 1) events.push(...sim.step(world, sameForAll(world, press({}))));
      expect(world.board.at({ col: 3, row: 3 })).toBe('empty');
      broken += 1;
      const drops = events.filter((e) => e.type === 'itemDropped');
      for (const drop of drops) {
        expect(drop.type === 'itemDropped' && sameCell(drop.cell, { col: 3, row: 3 })).toBe(true);
      }
      if (drops.length > 0) dropped += 1;
    }
    expect(broken).toBe(200);
    // 原型は 55%（Math.random() < 0.55）。200 回なら 40〜70% に収まる。
    expect(dropped / broken).toBeGreaterThan(0.4);
    expect(dropped / broken).toBeLessThan(0.7);
  });
});

describe('突進でぶつけたアイテム（原型 updateCharge の applyItem）', () => {
  /** ぞうを (3,5) から右へ、たまねぎを抱えて突進させ、(8,5) の相手にぶつける。相手が泣いた tick と長さ。 */
  function ram(victimAnimal: string): { hitAt: number | null; ticks: number | null } {
    const world = chargeArena(['elephant', victimAnimal]);
    const [elephant, victim] = world.players as [PlayerState, PlayerState];
    elephant.position = centerOf({ col: 3, row: 5 });
    victim.position = centerOf({ col: 8, row: 5 });
    // 傷は見ない（ぶつけたアイテムは無敵でも効く）。
    victim.invulnerableUntil = tick(9999);
    putItem(world, { col: 4, row: 5 }, 'onion');
    elephant.action = new ChargeAction('right');
    const sim = new Simulation();
    let hitAt: number | null = null;
    for (let t = 1; t <= 800; t += 1) {
      sim.step(world, sameForAll(world, press({})));
      if (hitAt === null && victim.effects.has('stun')) hitAt = t;
      if (hitAt !== null && !victim.effects.has('stun')) return { hitAt, ticks: t - hitAt };
    }
    return { hitAt, ticks: null };
  }

  it('ぶつけられた側の倍率がかかる：効果が2倍の動物は、ぶつけられたたまねぎで2倍泣く', () => {
    // 原型：たまねぎを抱えた突進を (8,5) の相手に当てると、うさぎ 180・かえる 360 フレーム泣く
    // （原型は小数の引き算で1フレーム長く出る。この版は 179・359。差の 180 は同じ）。
    const rabbit = ram('rabbit');
    const frog = ram('frog');
    expect(frog.hitAt).toBe(rabbit.hitAt);
    expect({ rabbit: rabbit.ticks, frog: frog.ticks }).toEqual({ rabbit: 179, frog: 359 });
  });
});

describe('突進で押しのける先（原型 updateCharge の collides）', () => {
  /** ぞうを (from,5) から右へ突進させ、押される側を (victimAt,5) に置く。押された最初の tick を返す。 */
  function knock(setup: {
    from: number;
    victimAt: number;
    victim?: string;
    soft?: number;
    bomb?: { owner: 0 | 1; col: number };
  }) {
    const world = chargeArena(['elephant', setup.victim ?? 'rabbit']);
    const [elephant, victim] = world.players as [PlayerState, PlayerState];
    elephant.position = centerOf({ col: setup.from, row: 5 });
    victim.position = centerOf({ col: setup.victimAt, row: 5 });
    // 原型を測ったときと同じ体力（爆風3回ぶん）。体当たりの傷で倒れると、押される先を見られない。
    victim.hp = 6;
    if (setup.soft !== undefined) world.board.set({ col: setup.soft, row: 5 }, 'soft');
    if (setup.bomb !== undefined) {
      const owner = world.players[setup.bomb.owner]!;
      owner.maxBombs = 5;
      const bomb = placeBombAt(world, owner, { col: setup.bomb.col, row: 5 });
      if (bomb === undefined) throw new Error('爆弾を置けなかった');
      bomb.fuse = tick(9999);
    }
    const hp = victim.hp;
    elephant.action = new ChargeAction('right');
    const sim = new Simulation();
    let firstPush: { i: number; x: number; tile: string; bomb: boolean } | null = null;
    const tiles: string[] = [];
    for (let i = 0; i < 60; i += 1) {
      const before = victim.position.x;
      sim.step(world, sameForAll(world, press({})));
      const cell = cellOf(victim.position);
      tiles.push(world.board.at(cell));
      if (firstPush === null && victim.position.x !== before) {
        firstPush = {
          i,
          x: victim.position.x,
          tile: world.board.at(cell),
          bomb: world.bombs.some((bomb) => sameCell(bomb.cell, cell)),
        };
      }
    }
    return { world, victim, firstPush, tiles, hpLost: hp - victim.hp };
  }

  it('外周の壁を背にした相手は押されずその場に残り、傷だけ受ける', () => {
    const { victim, firstPush, hpLost } = knock({ from: 17, victimAt: 21 });
    expect(firstPush).toBeNull();
    expect(victim.position.x).toBeCloseTo(21.5, 5);
    // 原型は体力 3→2（1つぶん）。この版は半分の単位で持つので 2。
    expect(hpLost).toBe(2);
  });

  it('壊せるブロックを背にした相手は、ぞうがそのブロックを壊した tick に初めて押される（原型 f20）', () => {
    const { firstPush, victim, tiles } = knock({ from: 15, victimAt: 19, soft: 20 });
    expect(firstPush).toMatchObject({ i: 20, tile: 'empty' });
    expect(firstPush?.x).toBeCloseTo(20.6, 5);
    expect(victim.position.x).toBeCloseTo(20.6, 5);
    expect(tiles.every((tile) => tile === 'empty')).toBe(true);
  });

  it('爆弾を背にした相手は、ぞうがその爆弾を起爆した tick に初めて押され、爆弾のマスには乗らない（原型 f20）', () => {
    const { firstPush, victim } = knock({ from: 15, victimAt: 19, bomb: { owner: 1, col: 20 } });
    expect(firstPush).toMatchObject({ i: 20, bomb: false });
    expect(victim.position.x).toBeCloseTo(20.6, 5);
  });

  it('対照：壊せるブロックを抜けられる相手（もぐら）は、ブロックの中へ押される（原型 f16）', () => {
    // 押す先の確かめに、押される側の抜けられる判定を渡しているかを見る。
    const { firstPush } = knock({ from: 15, victimAt: 19, soft: 20, victim: 'mole' });
    expect(firstPush).toMatchObject({ i: 16, tile: 'soft' });
  });

  it('抜けられる相手でも、ほかのプレイヤーの爆弾の隣のブロックへは押されない（原型 f20）', () => {
    const { firstPush } = knock({ from: 15, victimAt: 19, soft: 20, victim: 'mole', bomb: { owner: 0, col: 21 } });
    expect(firstPush).toMatchObject({ i: 20, tile: 'empty' });
  });
});

describe('突進中のぞうはふつうの拾いをしない（原型 update の `if (!p.effects.charge) pickupCheck(p)`）', () => {
  it('突進中は足元のハズレを拾わない。突進していなければ拾う', () => {
    const world = makeWorld(1, ['elephant', 'rabbit']);
    world.items = [];
    const [elephant, rabbit] = world.players as [PlayerState, PlayerState];
    elephant.position = { x: 3.5, y: 3.5 };
    elephant.action = new ChargeAction('right');
    rabbit.position = { x: 5.5, y: 5.5 };
    putItem(world, { col: 3, row: 3 }, 'onion');
    putItem(world, { col: 5, row: 5 }, 'onion');
    const events = new ItemSystem().step(world);
    expect(events.filter((e) => e.type === 'itemTaken' && e.taker === elephant.id)).toEqual([]);
    expect(elephant.effects.has('stun')).toBe(false);
    expect(world.items.map((item) => `${item.cell.col},${item.cell.row}`)).toEqual(['3,3']);
    expect(rabbit.effects.has('stun')).toBe(true);
  });

  it('止まったぞうの撒いたハズレを、突進中のもう1頭は抱えて運ぶ（原型：泣くのは止まっていた側、f30）', () => {
    const world = chargeArena(['elephant', 'elephant']);
    const [a, b] = world.players as [PlayerState, PlayerState];
    a.position = { x: 2.91, y: 15.5 };
    b.position = { x: 9.5, y: 10.5 };
    a.action = new ChargeAction('right');
    b.action = new ChargeAction('down');
    putItem(world, { col: 9, row: 11 }, 'onion');
    const sim = new Simulation();
    let aStun: number | null = null;
    let bStun: number | null = null;
    for (let i = 0; i < 120; i += 1) {
      sim.step(world, sameForAll(world, press({})));
      if (aStun === null && a.effects.has('stun')) aStun = i;
      if (bStun === null && b.effects.has('stun')) bStun = i;
    }
    expect(aStun).toBeNull();
    expect(bStun).toBe(30);
  });
});

describe('突進中に倒れたら、抱えていたハズレは盤面に出ない（原型 update の `if (p.state===\'ALIVE\')`）', () => {
  it('抱えたまま突進で爆弾に突っ込み、その爆風で倒れても、たまねぎは出ない（原型 f25）', () => {
    const world = chargeArena(['elephant', 'rabbit']);
    const [elephant, rabbit] = world.players as [PlayerState, PlayerState];
    elephant.position = centerOf({ col: 1, row: 3 });
    rabbit.position = centerOf({ col: 20, row: 15 });
    elephant.hp = 1;
    putItem(world, { col: 3, row: 3 }, 'onion');
    rabbit.maxBombs = 5;
    const bomb = placeBombAt(world, rabbit, { col: 7, row: 3 });
    if (bomb === undefined) throw new Error('爆弾を置けなかった');
    bomb.fuse = tick(9999);
    elephant.action = new ChargeAction('right');
    const sim = new Simulation();
    let downAt: number | null = null;
    const drops: SimEvent[] = [];
    for (let i = 0; i < 120; i += 1) {
      const events = sim.step(world, sameForAll(world, press({})));
      if (downAt === null && !isAlive(elephant)) downAt = i;
      drops.push(...events.filter((e) => e.type === 'itemDropped' && e.kind === 'onion'));
    }
    expect(downAt).toBe(25);
    expect(drops).toEqual([]);
    expect(world.items.filter((item) => item.kind === 'onion')).toEqual([]);
  });

  it('抱えた直後に倒されても、たまねぎは出ない', () => {
    const world = chargeArena(['elephant', 'rabbit']);
    const [elephant, rabbit] = world.players as [PlayerState, PlayerState];
    elephant.position = centerOf({ col: 1, row: 1 });
    rabbit.position = centerOf({ col: 20, row: 15 });
    putItem(world, { col: 2, row: 1 }, 'onion');
    elephant.action = new ChargeAction('right');
    const sim = new Simulation();
    for (let i = 0; i < 3; i += 1) sim.step(world, sameForAll(world, press({})));
    expect(world.items).toEqual([]);
    elephant.hp = 1;
    hurt(world, elephant, rabbit.id, 2);
    expect(isAlive(elephant)).toBe(false);
    const events: SimEvent[] = [];
    for (let i = 0; i < 5; i += 1) events.push(...sim.step(world, sameForAll(world, press({}))));
    expect(events.filter((e) => e.type === 'itemDropped' && e.kind === 'onion')).toEqual([]);
    expect(world.items.filter((item) => item.kind === 'onion')).toEqual([]);
  });
});
