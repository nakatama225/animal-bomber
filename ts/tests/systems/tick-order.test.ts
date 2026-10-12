import { describe, expect, it } from 'vitest';

import { PitActor } from '../../src/domain/abilities/mole/PitAction.js';
import { BurntTongueActor, TongueAction, tongueReachOf } from '../../src/domain/abilities/frog/TongueAction.js';
import type { WorldActor } from '../../src/domain/abilities/WorldActor.js';
import { ActorSystem } from '../../src/domain/systems/ActorSystem.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
import { centerOf, type Cell } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import { placeBombAt } from '../../src/domain/mutations/bombs.js';
import type { PlayerState } from '../../src/domain/state/PlayerState.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { clearBoard, makeWorld, onlyFor, press, sameForAll } from '../helpers.js';

/*
 * 1 tick の中の並び（`Simulation` の説明）が原型の update と同じであることの検査。
 * 期待値は、原型（legacy/animal-bomber.html）を画面なしで動かして、同じ場面で測った答え。
 */

function arena(animals: [string, string]): { world: WorldState; p0: PlayerState; p1: PlayerState } {
  const world = makeWorld(5, animals);
  clearBoard(world);
  world.items = [];
  const p0 = world.players[0]!;
  const p1 = world.players[1]!;
  for (const player of world.players) player.invulnerableUntil = tick(0);
  return { world, p0, p1 };
}

function place(player: PlayerState, cell: Cell): void {
  player.position = centerOf(cell);
}

describe('1 tick の中の並び（原型の update と同じ）', () => {
  it('拾うのは爆発より先：爆発する tick に踏み込んだアイテムは、焼ける前に拾える', () => {
    const { world, p0: fox, p1: frog } = arena(['fox', 'frog']);
    fox.position = { x: 4.99, y: 7.5 };
    fox.invulnerableUntil = tick(9999);
    place(frog, { col: 19, row: 13 });
    world.items.push({ id: world.ids.take(), cell: { col: 5, row: 7 }, kind: 'fire' });
    frog.power = 3;
    const bomb = placeBombAt(world, frog, { col: 3, row: 7 })!;
    bomb.fuse = tick(1);
    const before = fox.power;
    const events = new Simulation().step(world, onlyFor(world, 0, press({ right: true })));
    expect(events.some((e) => e.type === 'exploded')).toBe(true);
    expect(fox.power - before).toBe(1);
    expect(world.items).toEqual([]);
    expect(fox.position.x).toBeCloseTo(5.051667, 5);
  });

  it('技を始めるのは動いたあと：とくぎが出る tick にだけ右を押すと、右へ進む', () => {
    // 原型：下を向いたぞうが技のボタンを押し続け、出るフレームにだけ右を押すと、右へ突進する。
    const { world, p0: elephant, p1: frog } = arena(['elephant', 'frog']);
    place(elephant, { col: 3, row: 7 });
    place(frog, { col: 19, row: 13 });
    elephant.facing = 'down';
    elephant.specialCharges = 1;
    // ラウンドの途中の、何も押していない状態にする（ラウンドの始まりは、とくぎを出し終えた扱い）。
    elephant.actionFired = false;
    const sim = new Simulation();
    const hold = abilityOf('elephant').holdTicks;
    for (let t = 1; t <= hold; t += 1) {
      sim.step(world, onlyFor(world, 0, press({ action: true, right: t === hold })));
    }
    expect(elephant.action?.kind).toBe('charge');
    expect(elephant.facing).toBe('right');
    const x = elephant.position.x;
    sim.step(world, onlyFor(world, 0, press({ action: true })));
    expect(elephant.position.x).toBeGreaterThan(x);
    expect(elephant.position.y).toBe(7.5);
  });

  it('動く・置くはプレイヤーごと：1P が足元に置いた tick に、2P はその爆弾に阻まれて動けない', () => {
    const { world, p0, p1 } = arena(['fox', 'fox']);
    place(p0, { col: 3, row: 7 });
    p1.position = { x: 4.37, y: 7.5 };
    new Simulation().step(
      world,
      new Map([
        [0, press({ bomb: true })],
        [1, press({ left: true })],
      ]),
    );
    expect(p1.position.x).toBe(4.37);
    expect([...world.bombs[0]!.passThrough]).toEqual([0]);
  });

  it('状態の時間はプレイヤーごとに減らす：押しつけられた側の番号で、泣く長さが 1 tick 違う', () => {
    // 原型：番号の大きいプレイヤーへ押しつけると 180 フレーム、小さいプレイヤーへは 181 フレーム泣く。
    // 原型は経過秒を小数で引いていくので、どちらも1フレーム長く出る（この版は 179・180）。差の1は同じ。
    const stunned = (elephantFirst: boolean): number => {
      const { world, p0, p1 } = arena(elephantFirst ? ['elephant', 'fox'] : ['fox', 'elephant']);
      const elephant = elephantFirst ? p0 : p1;
      const fox = elephantFirst ? p1 : p0;
      place(elephant, { col: 3, row: 7 });
      place(fox, { col: 6, row: 7 });
      fox.invulnerableUntil = tick(9999);
      world.items.push({ id: world.ids.take(), cell: { col: 4, row: 7 }, kind: 'onion' });
      elephant.facing = 'right';
      elephant.action = abilityOf('elephant').onHold!(world, elephant).action;
      const sim = new Simulation();
      let frames = 0;
      for (let t = 0; t < 400; t += 1) {
        sim.step(world, sameForAll(world, press({})));
        if (fox.effects.has('stun')) frames += 1;
      }
      return frames;
    };
    expect(stunned(true)).toBe(179);
    expect(stunned(false)).toBe(180);
  });

  it('伸びている舌は、爆風が出た tick のうちに焼き切れる（被弾を見たあとに確かめる）', () => {
    const { world, p0: frog, p1: fox } = arena(['frog', 'fox']);
    place(frog, { col: 3, row: 7 });
    place(fox, { col: 19, row: 13 });
    frog.invulnerableUntil = tick(9999);
    frog.action = new TongueAction({ col: 3, row: 7 }, 'right');
    const sim = new Simulation();
    for (let t = 0; t < 20; t += 1) sim.step(world, sameForAll(world, press({})));
    fox.power = 2;
    const bomb = placeBombAt(world, fox, { col: 5, row: 9 })!;
    bomb.fuse = tick(1);
    sim.step(world, sameForAll(world, press({})));
    expect(frog.action).toBeNull();
    expect(frog.effects.has('stun')).toBe(true);
    expect(tongueReachOf(world, frog)).toBe(1);
  });

  it('焼けた舌が戻るのは、持ち主の振る舞いを進める前：戻る tick に伸びる舌は、戻った長さまで伸びる', () => {
    // 原型：焼けて3マスまでの舌の4マス先にアイテム。3マス目が伸びるのは 23 フレーム目。戻るのが
    // 23 フレーム目までなら4マス伸びて掴み（61 フレーム目に終わる）、24 フレーム目なら3マスで引っ込む（46）。
    const run = (regenAt: number): { end: number; gained: number } => {
      const { world, p0: frog, p1: rabbit } = arena(['frog', 'rabbit']);
      place(frog, { col: 3, row: 5 });
      place(rabbit, { col: 19, row: 13 });
      const scar = new BurntTongueActor(frog.id, 3);
      while (scar.untilRegen > regenAt) scar.tick();
      world.actors.push(scar);
      world.items.push({ id: world.ids.take(), cell: { col: 7, row: 5 }, kind: 'fire' });
      frog.action = new TongueAction({ col: 3, row: 5 }, 'right');
      const before = frog.power;
      const sim = new Simulation();
      let end = 0;
      for (let t = 1; t <= 120 && end === 0; t += 1) {
        sim.step(world, sameForAll(world, press({})));
        if (frog.action === null) end = t;
      }
      return { end, gained: frog.power - before };
    };
    expect(run(23)).toEqual({ end: 61, gained: 2 });
    expect(run(24)).toEqual({ end: 46, gained: 0 });
  });

  it('落とし穴に落ちるのは拾ったあと：穴の上のバナナを踏んでも、穴を抜けたあと滑らない', () => {
    // 原型：右へ歩いたかえるは 9 フレーム目に落ち、滑りは穴が消す。200 フレームたっても x = 4.055 のまま。
    const { world, p0: frog, p1: mole } = arena(['frog', 'mole']);
    place(frog, { col: 3, row: 7 });
    place(mole, { col: 19, row: 13 });
    world.actors.push(new PitActor({ col: 4, row: 7 }, 1));
    world.items.push({ id: world.ids.take(), cell: { col: 4, row: 7 }, kind: 'banana' });
    const sim = new Simulation();
    let fellAt: number | null = null;
    for (let t = 1; t <= 30 && fellAt === null; t += 1) {
      sim.step(world, onlyFor(world, 0, press({ right: true })));
      if (frog.effects.has('pitfall')) fellAt = t;
    }
    expect(fellAt).toBe(9);
    expect(frog.effects.has('slide')).toBe(false);
    for (let t = 0; t < 200; t += 1) sim.step(world, sameForAll(world, press({})));
    expect(frog.effects.has('slide')).toBe(false);
    expect(frog.position.x).toBeCloseTo(4.055, 5);
  });
});

describe('盤面の物を進める順（`WorldActor.turn`）', () => {
  /** 進めた順を書き込むだけの盤面の物。 */
  function fake(name: string, turn: number | 'owner', owner: 0 | 1, log: string[]): WorldActor {
    return {
      kind: name,
      turn,
      owner,
      tick: () => {
        log.push(name);
        return { events: [], done: name.endsWith('!') };
      },
      encode: () => name,
    };
  }

  it('数の小さい順に進め（同じ数は出た順）、盤面の物の並びは出た順のまま残す', () => {
    const world = makeWorld();
    const log: string[] = [];
    world.actors = [fake('slime', 4, 0, log), fake('pit-a', 0, 0, log), fake('chaser!', 2, 1, log), fake('pit-b', 0, 1, log)];
    new ActorSystem().step(world);
    expect(log).toEqual(['pit-a', 'pit-b', 'chaser!', 'slime']);
    expect(world.actors.map((actor) => actor.kind)).toEqual(['slime', 'pit-a', 'pit-b']);
  });

  it('持ち主の番に進めるものは、そのプレイヤーの番にだけ進め、プレイヤーが動いたあとの番では進めない', () => {
    const world = makeWorld();
    const log: string[] = [];
    world.actors = [fake('scar-0', 'owner', 0, log), fake('scar-1', 'owner', 1, log), fake('pit', 0, 0, log)];
    const actors = new ActorSystem();
    actors.stepOwnedBy(world, world.players[1]!);
    expect(log).toEqual(['scar-1']);
    actors.step(world);
    expect(log).toEqual(['scar-1', 'pit']);
  });
});
