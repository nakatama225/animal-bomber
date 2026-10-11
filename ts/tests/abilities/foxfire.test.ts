import { describe, expect, it } from 'vitest';

import { ChargeAction } from '../../src/domain/abilities/elephant/ChargeAction.js';
import { FoxfireActor } from '../../src/domain/abilities/fox/FoxfireActor.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
import { cellOf, centerOf, type Cell } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import { addBlast } from '../../src/domain/mutations/explode.js';
import type { PlayerState } from '../../src/domain/state/PlayerState.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { clearBoard, makeWorld, onlyFor, press, sameForAll } from '../helpers.js';

/*
 * きつねの狐火とキツネ跳び、突進どうしの体当たりを、原型（legacy/animal-bomber.html の castFoxfire・
 * foxfireStep・updateFoxfires・useSpecial のきつね・updateCharge）に合わせる。
 * 期待値は原型を画面なしで動かして測った値。原型はとくぎを出した直後のフレームを 1 と数えた。
 * ここでは炎を直に置き、最初の tick を 1 と数える。
 */

function arena(animals: [string, string]): { world: WorldState; p0: PlayerState; p1: PlayerState } {
  const world = makeWorld(5, animals);
  clearBoard(world);
  world.items = [];
  const [p0, p1] = world.players as [PlayerState, PlayerState];
  for (const player of world.players) player.invulnerableUntil = tick(0);
  return { world, p0, p1 };
}

function place(player: PlayerState, cell: Cell): void {
  player.position = centerOf(cell);
}

/** 値が変わった tick だけを「tick:値」で並べる。 */
function changes(log: readonly string[]): string[] {
  return log.flatMap((value, i) => (i === 0 || value !== log[i - 1] ? [`${i + 1}:${value}`] : []));
}

/** 炎だけを進め、毎 tick の炎のマス（消えたら '-'）と、1番の体力を記録する。 */
function runFire(world: WorldState, fire: FoxfireActor, ticks = 120): { cells: string[]; hp: string[] } {
  const cells: string[] = [];
  const hp: string[] = [];
  let done = false;
  for (let t = 0; t < ticks; t += 1) {
    if (!done) done = fire.tick(world).done;
    const cell = cellOf(fire.position);
    cells.push(done ? '-' : `${cell.col},${cell.row}`);
    hp.push(`${world.players[1]!.hp}`);
  }
  return { cells, hp };
}

describe('狐火の進み方（原型 foxfireStep・updateFoxfires）', () => {
  it('k マス目を floor(10.2k)+1 tick 目に進み、91 tick 目に消える', () => {
    const { world, p0: fox, p1: rabbit } = arena(['fox', 'rabbit']);
    place(fox, { col: 3, row: 7 });
    place(rabbit, { col: 19, row: 7 });
    const { cells } = runFire(world, new FoxfireActor(fox.position, fox.id));
    expect(changes(cells)).toEqual([
      '1:3,7', '11:4,7', '21:5,7', '31:6,7', '41:7,7', '52:8,7', '62:9,7', '72:10,7', '82:11,7', '91:-',
    ]);
  });

  it('ブロックを回り込む最短の道を進む', () => {
    const { world, p0: fox, p1: rabbit } = arena(['fox', 'rabbit']);
    place(fox, { col: 3, row: 7 });
    place(rabbit, { col: 8, row: 7 });
    for (const row of [6, 7, 8]) world.board.set({ col: 5, row }, 'soft');
    const before = rabbit.hp;
    const { cells } = runFire(world, new FoxfireActor(fox.position, fox.id));
    expect(changes(cells)).toEqual([
      '1:3,7', '11:3,8', '21:3,9', '31:4,9', '41:5,9', '52:6,9', '62:7,9', '72:7,8', '82:7,7', '91:-',
    ]);
    expect(rabbit.hp).toBe(before);
  });

  it('相手に当たっても消えず、相手のマスに居続ける（被弾のあとの無敵の間は2度当たらない）', () => {
    const { world, p0: fox, p1: rabbit } = arena(['fox', 'rabbit']);
    place(fox, { col: 3, row: 7 });
    place(rabbit, { col: 5, row: 7 });
    const before = rabbit.hp;
    const { cells, hp } = runFire(world, new FoxfireActor(fox.position, fox.id));
    expect(changes(cells)).toEqual(['1:3,7', '11:4,7', '21:5,7', '91:-']);
    expect(changes(hp)).toEqual([`1:${before}`, `21:${before - 2}`]);
  });

  it('突進中のぞうにも当たる（傷は上限で 0.5 に減る）', () => {
    // 原型：右から左へ突進してくるぞうと 31 フレーム目にすれ違い、体力が 0.5 減る。
    const { world, p0: fox, p1: elephant } = arena(['fox', 'elephant']);
    place(fox, { col: 3, row: 7 });
    place(elephant, { col: 12, row: 7 });
    elephant.facing = 'left';
    elephant.action = new ChargeAction('left');
    world.actors.push(new FoxfireActor(fox.position, fox.id));
    const sim = new Simulation();
    const hp: string[] = [];
    for (let t = 0; t < 40; t += 1) {
      sim.step(world, sameForAll(world, press({})));
      hp.push(`${elephant.hp}`);
    }
    expect(changes(hp)).toEqual(['1:8', '31:7']);
  });
});

describe('キツネ跳び（原型 useSpecial のきつね・isBlastProof）', () => {
  /** きつねにとくぎを出させる。出した tick のあとの世界を返す。 */
  function leap(): { world: WorldState; fox: PlayerState; sim: Simulation } {
    const { world, p0: fox, p1: rabbit } = arena(['fox', 'rabbit']);
    place(fox, { col: 3, row: 7 });
    place(rabbit, { col: 19, row: 7 });
    fox.specialCharges = 1;
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    for (let i = 0; i < abilityOf('fox').holdTicks; i += 1) sim.step(world, onlyFor(world, 0, press({ action: true })));
    return { world, fox, sim };
  }

  it('跳んでいるのは 1 秒（原型 59 フレーム、この版は出した tick の終わりから数えて 59 tick）', () => {
    const { world, fox, sim } = leap();
    expect(fox.effects.has('leap')).toBe(true);
    let leaping = 1;
    for (let t = 0; t < 120; t += 1) {
      sim.step(world, sameForAll(world, press({})));
      if (fox.effects.has('leap')) leaping += 1;
    }
    expect(leaping).toBe(59);
  });

  it('跳んでいる間は爆風が当たらない（対照：跳び終わったあとは当たる）', () => {
    const { world, fox, sim } = leap();
    const before = fox.hp;
    addBlast(world, cellOf(fox.position), 1, false);
    for (let t = 0; t < 10; t += 1) sim.step(world, sameForAll(world, press({})));
    expect(fox.hp).toBe(before);

    while (fox.effects.has('leap')) sim.step(world, sameForAll(world, press({})));
    addBlast(world, cellOf(fox.position), 1, false);
    sim.step(world, sameForAll(world, press({})));
    expect(fox.hp).toBeLessThan(before);
  });
});

describe('突進どうしの体当たり（原型 updateCharge は相手の突進を見ない）', () => {
  it('向かい合って突進すると、どちらにも傷が入る（0.5 ずつ）', () => {
    // 原型：0番が 14 フレーム目、1番が 17 フレーム目に 0.5 ずつ減る。
    const { world, p0: a, p1: b } = arena(['elephant', 'elephant']);
    place(a, { col: 3, row: 7 });
    place(b, { col: 9, row: 7 });
    a.facing = 'right';
    b.facing = 'left';
    a.action = new ChargeAction('right');
    b.action = new ChargeAction('left');
    const sim = new Simulation();
    const hp: string[] = [];
    for (let t = 0; t < 40; t += 1) {
      sim.step(world, sameForAll(world, press({})));
      hp.push(`${a.hp}/${b.hp}`);
    }
    expect(changes(hp)).toEqual(['1:8/8', '14:7/8', '17:7/7']);
  });
});
