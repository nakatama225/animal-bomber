import { describe, expect, it } from 'vitest';

import { ChargeAction } from '../../src/domain/abilities/elephant/ChargeAction.js';
import { FoxfireActor } from '../../src/domain/abilities/fox/FoxfireActor.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
import { cellOf, centerOf, type Cell } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import { addBlast } from '../../src/domain/mutations/explode.js';
import { OUT } from '../../src/domain/state/Life.js';
import { isAlive, type PlayerState } from '../../src/domain/state/PlayerState.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { ActorSystem } from '../../src/domain/systems/ActorSystem.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { clearBoard, grantSpecial, makeWorld, onlyFor, press, sameForAll } from '../helpers.js';

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

/** 炎のいるマスを「列,行」で。 */
function cellText(fire: FoxfireActor): string {
  const cell = cellOf(fire.position);
  return `${cell.col},${cell.row}`;
}

/**
 * 炎だけを盤面の物として進め（`ActorSystem`。動かしてから当たりを見る）、毎 tick の炎のマス（消えたら '-'）と、
 * 1番の体力を記録する。
 */
function runFire(world: WorldState, fire: FoxfireActor, ticks = 120): { cells: string[]; hp: string[] } {
  const actors = new ActorSystem();
  world.actors.push(fire);
  const cells: string[] = [];
  const hp: string[] = [];
  for (let t = 0; t < ticks; t += 1) {
    actors.step(world);
    cells.push(world.actors.includes(fire) ? cellText(fire) : '-');
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
    // 原型を測ったときと同じ体力（爆風3回ぶん＋ぞうの上乗せ1回ぶん）。
    elephant.hp = 8;
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

describe('同じ tick の炎どうし（原型 updateFoxfires は全部の炎を動かしてから、別の輪で当たりを見る）', () => {
  it('古い炎が相手を倒す tick に、新しい炎もその相手のほうへ一歩進む', () => {
    // 原型：11 フレーム目に、古い炎が (5,7) へ進んで当たり、相手は外周へ回る。新しい炎も同じフレームに
    // (8,7) へ進む（当たりを見る前に、全部の炎が動き終わっている）。炎ごとに動いてすぐ当たる形だと、
    // 新しい炎が動くときには相手がもう盤面にいないので、(9,7) から動かない。
    const { world, p0: fox, p1: rabbit } = arena(['fox', 'rabbit']);
    place(fox, { col: 3, row: 7 });
    place(rabbit, { col: 5, row: 7 });
    // 1回当たると倒れる体力（原型の体力 1）。
    rabbit.hp = 2;
    const older = new FoxfireActor(centerOf({ col: 4, row: 7 }), fox.id);
    const newer = new FoxfireActor(centerOf({ col: 9, row: 7 }), fox.id);
    world.actors.push(older, newer);
    const sim = new Simulation();
    const log: string[] = [];
    for (let t = 0; t < 11; t += 1) {
      sim.step(world, sameForAll(world, press({})));
      log.push(`${cellText(older)} ${cellText(newer)} ${isAlive(rabbit) ? 'board' : 'down'}`);
    }
    expect(changes(log)).toEqual(['1:4,7 9,7 board', '11:5,7 8,7 down']);
  });

  it('同じ tick に2つの炎が当たると、古い炎の当たりが先', () => {
    // 原型：11 フレーム目に、0番の炎（古い）が 1番に、1番の炎（新しい）が 0番に当たる。被弾のたびに吐き出す
    // アイテムは (9,7) → (3,7) の順に積まれた（当たりの輪は炎の配列を前から順に処理する。L2685）。
    const { world, p0, p1 } = arena(['fox', 'fox']);
    place(p0, { col: 3, row: 7 });
    place(p1, { col: 9, row: 7 });
    world.actors.push(
      new FoxfireActor(centerOf({ col: 8, row: 7 }), p0.id),
      new FoxfireActor(centerOf({ col: 4, row: 7 }), p1.id),
    );
    const sim = new Simulation();
    const hits: string[] = [];
    for (let t = 1; t <= 11; t += 1) {
      const events = sim.step(world, sameForAll(world, press({})));
      for (const event of events) if (event.type === 'playerHurt') hits.push(`${t}:${event.target}`);
    }
    expect(hits).toEqual(['11:1', '11:0']);
    expect(world.items.map((item) => `${item.cell.col},${item.cell.row}`)).toEqual(['9,7', '3,7']);
  });

  it('寿命が尽きる tick（91 tick 目）には、炎のマスにいる相手にも当たらない（対照：90 tick 目なら当たる）', () => {
    // 原型は寿命が尽きた炎を動かす輪の中で外す（L2679-2682）ので、その炎は当たりの輪（L2685）に残らない。
    // 原型：無敵が 91 フレーム目に切れると当たらず、90 フレーム目に切れると 90 フレーム目に当たる。炎は 91 フレーム目に消える。
    const hitAt = (vulnerableFrom: number): number | null => {
      const { world, p0: fox, p1: rabbit } = arena(['fox', 'rabbit']);
      place(fox, { col: 3, row: 7 });
      place(rabbit, { col: 5, row: 7 });
      // t tick 目の間の時刻（world.now）は t - 1。
      rabbit.invulnerableUntil = tick(vulnerableFrom - 1);
      world.actors.push(new FoxfireActor(rabbit.position, fox.id));
      const before = rabbit.hp;
      const sim = new Simulation();
      for (let t = 1; t <= 100; t += 1) {
        sim.step(world, sameForAll(world, press({})));
        if (rabbit.hp < before) return t;
      }
      return null;
    };
    expect(hitAt(91)).toBeNull();
    expect(hitAt(90)).toBe(90);
  });
});

describe('キツネ跳び（原型 useSpecial のきつね・isBlastProof）', () => {
  /** きつねにとくぎを出させる。出した tick のあとの世界を返す。 */
  function leap(): { world: WorldState; fox: PlayerState; sim: Simulation } {
    const { world, p0: fox, p1: rabbit } = arena(['fox', 'rabbit']);
    place(fox, { col: 3, row: 7 });
    place(rabbit, { col: 19, row: 7 });
    grantSpecial(fox, 1);
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    for (let i = 0; i < abilityOf('fox').holdTicks; i += 1) sim.step(world, onlyFor(world, 0, press({ action: true })));
    return { world, fox, sim };
  }

  it('跳んでいるのは 1 秒（出した tick を含めて 60 tick。原型は出したフレームのあと 59 フレーム）', () => {
    // 出した tick には状態の時間が減らず（減らすのは次の tick の頭。原型も同じ）、そのあと 59 tick 続く。
    const { world, fox, sim } = leap();
    expect(fox.effects.has('leap')).toBe(true);
    let after = 0;
    for (let t = 0; t < 120; t += 1) {
      sim.step(world, sameForAll(world, press({})));
      if (fox.effects.has('leap')) after += 1;
    }
    expect(after).toBe(59);
  });

  it('盤面に相手が1人もいなければ、跳ぶだけで炎は出さない（原型の castFoxfire。チキンは使う）', () => {
    const { world, p0: fox, p1: rabbit } = arena(['fox', 'rabbit']);
    place(fox, { col: 3, row: 7 });
    rabbit.life = OUT;
    grantSpecial(fox, 1);
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    for (let i = 0; i < abilityOf('fox').holdTicks; i += 1) sim.step(world, onlyFor(world, 0, press({ action: true })));
    expect(fox.effects.has('leap')).toBe(true);
    expect(fox.specialCharges).toBe(0);
    expect(world.actors.some((actor) => actor instanceof FoxfireActor)).toBe(false);
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
    // 原型を測ったときと同じ体力（爆風3回ぶん＋ぞうの上乗せ1回ぶん）。
    a.hp = 8;
    b.hp = 8;
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

describe('跳び上がっている間と、同じマスの相手（原型 updateFoxfires・updateCharge の isBlastProof）', () => {
  it('跳び上がっている相手には、狐火が当たらない（対照：跳んでいなければ 21 tick 目に当たる）', () => {
    // きつねどうしの対戦で起きる。炎を放ったきつね自身は持ち主として除かれるので、相手もきつねにする。
    const hitBy = (leaping: boolean): string[] => {
      const { world, p0: fox, p1: other } = arena(['fox', 'fox']);
      place(fox, { col: 3, row: 7 });
      place(other, { col: 5, row: 7 });
      if (leaping) other.effects.add('leap', tick(60), tick(60));
      return changes(runFire(world, new FoxfireActor(fox.position, fox.id), 40).hp);
    };
    const { p1 } = arena(['fox', 'fox']);
    expect(hitBy(true)).toEqual([`1:${p1.hp}`]);
    expect(hitBy(false)).toEqual([`1:${p1.hp}`, `21:${p1.hp - 2}`]);
  });

  it('狐火は、乗ったマスにいる相手全員に当たる（最初の1人で止めない）', () => {
    const world = makeWorld(5, ['fox', 'rabbit', 'frog']);
    clearBoard(world);
    world.items = [];
    const [fox, rabbit, frog] = world.players as [PlayerState, PlayerState, PlayerState];
    for (const player of world.players) player.invulnerableUntil = tick(0);
    place(fox, { col: 3, row: 7 });
    place(rabbit, { col: 5, row: 7 });
    place(frog, { col: 5, row: 7 });
    const before = { rabbit: rabbit.hp, frog: frog.hp };
    world.actors.push(new FoxfireActor(fox.position, fox.id));
    const actors = new ActorSystem();
    const hitAt: { rabbit: number | null; frog: number | null } = { rabbit: null, frog: null };
    for (let t = 1; t <= 40; t += 1) {
      actors.step(world);
      if (hitAt.rabbit === null && rabbit.hp < before.rabbit) hitAt.rabbit = t;
      if (hitAt.frog === null && frog.hp < before.frog) hitAt.frog = t;
    }
    expect(hitAt).toEqual({ rabbit: 21, frog: 21 });
  });

  it('跳び上がっている相手には、突進の体当たりの傷が入らない（対照：跳んでいなければ入る）', () => {
    const hpAfter = (leaping: boolean): { before: number; after: number } => {
      const { world, p0: elephant, p1: fox } = arena(['elephant', 'fox']);
      place(elephant, { col: 3, row: 7 });
      place(fox, { col: 6, row: 7 });
      elephant.facing = 'right';
      elephant.action = new ChargeAction('right');
      if (leaping) fox.effects.add('leap', tick(60), tick(60));
      const before = fox.hp;
      const sim = new Simulation();
      for (let t = 0; t < 30; t += 1) sim.step(world, sameForAll(world, press({})));
      return { before, after: fox.hp };
    };
    const leaping = hpAfter(true);
    expect(leaping.after).toBe(leaping.before);
    const standing = hpAfter(false);
    expect(standing.after).toBeLessThan(standing.before);
  });
});
