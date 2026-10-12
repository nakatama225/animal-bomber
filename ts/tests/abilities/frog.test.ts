import { describe, expect, it } from 'vitest';

import { SlimeBombActor } from '../../src/domain/abilities/frog/SlimeBombActor.js';
import {
  BurntTongueActor,
  TONGUE_REACH,
  TongueAction,
  tongueReachOf,
} from '../../src/domain/abilities/frog/TongueAction.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
import { cellOf, centerOf, type Cell } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { placeBombAt } from '../../src/domain/mutations/bombs.js';
import { addBlast } from '../../src/domain/mutations/explode.js';
import { enterSuddenDeath } from '../../src/domain/mutations/suddenDeath.js';
import { OUT } from '../../src/domain/state/Life.js';
import { isFrozen, type PlayerState } from '../../src/domain/state/PlayerState.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { clearBoard, makeWorld, onlyFor, press, sameForAll } from '../helpers.js';

/*
 * かえるの粘膜爆弾と舌を、原型（legacy/animal-bomber.html の frogSlime・slimeBurst・updateSlimes・updateTongue）に
 * 合わせる。期待値は原型を画面なしで動かして測った値。
 *
 * ⚠️ 跳ぶ向きの混ぜ方は原型と揃わない（原型は比較の関数に乱数を返す並べ替えで、並びが実行環境しだい）。
 * 跳ぶ先は「どのマスに着地しうるか」の集まりで比べる。
 */

function arena(seed = 2468): { world: WorldState; frog: PlayerState; rabbit: PlayerState } {
  const world = makeWorld(seed, ['frog', 'rabbit']);
  clearBoard(world);
  world.items = [];
  const [frog, rabbit] = world.players as [PlayerState, PlayerState];
  frog.position = centerOf({ col: 1, row: 13 });
  rabbit.position = centerOf({ col: 19, row: 1 });
  return { world, frog, rabbit };
}

/** 粘膜爆弾の actor だけを、終わるまで進める（ほかの System を通さない。上限 200 tick）。 */
function runUntilDone(world: WorldState, actor: SlimeBombActor): SimEvent[] {
  const events: SimEvent[] = [];
  for (let i = 0; i < 200; i += 1) {
    const result = actor.tick(world);
    events.push(...result.events);
    if (result.done) return events;
  }
  throw new Error('粘膜爆弾が 200 tick たっても終わらない');
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
    const events = runUntilDone(world, new SlimeBombActor({ col: 6, row: 7 }, frog, 1));
    expect(events.some((e) => e.type === 'exploded')).toBe(true);
    expect(blastCells(world)).toEqual(['6,7C', '7,7', '5,7']);
  });

  it('柱の上で跳ね終わったら、隣の空きマスへずれて爆発する（原型の順で最初は右）', () => {
    const { world, frog } = arena();
    runUntilDone(world, new SlimeBombActor({ col: 8, row: 8 }, frog, 1));
    expect(blastCells(world)).toEqual(['9,8C', '9,9', '9,7']);
  });

  it('壊せるブロックの上なら、隣へずれて爆発し、そのブロックは爆風で壊れる', () => {
    const { world, frog } = arena();
    world.board.set({ col: 6, row: 7 }, 'soft');
    runUntilDone(world, new SlimeBombActor({ col: 6, row: 7 }, frog, 1));
    expect(blastCells(world)[0]).toBe('7,7C');
    expect(world.board.at({ col: 6, row: 7 })).toBe('empty');
  });

  it('爆弾の上なら、隣へずれて爆発し、その爆弾も誘爆する', () => {
    const { world, frog, rabbit } = arena();
    bombWithLongFuse(world, rabbit, { col: 6, row: 7 });
    runUntilDone(world, new SlimeBombActor({ col: 6, row: 7 }, frog, 1));
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
    const events = runUntilDone(world, new SlimeBombActor({ col: 8, row: 8 }, frog, 1));
    expect(blastCells(world)).toEqual(['8,8C']);
    expect(around.every((cell) => world.board.at(cell) === 'soft')).toBe(true);
    expect(world.bombs).toEqual([]);
    expect(events.filter((e) => e.type === 'exploded')).toHaveLength(1);
  });

  it('本物の爆弾を出したままでも爆発し、その爆弾は残る（手持ちの数も変わらない）', () => {
    // ⚠️ 原型は置いている数（activeBombs）を1つ多く引く（生やして +1、すぐ −1、爆発でもう −1）。
    // ほかに爆弾を出していると、上限より1つ多く置けるようになる。原型の注記「手持ちは減らさない」の
    // 意図に合わせ、この版は差し引きで変えない。
    const { world, frog } = arena();
    bombWithLongFuse(world, frog, { col: 3, row: 13 });
    const before = frog.activeBombs;
    runUntilDone(world, new SlimeBombActor({ col: 6, row: 7 }, frog, 1));
    expect(blastCells(world)[0]).toBe('6,7C');
    expect(world.bombs.map((bomb) => `${bomb.cell.col},${bomb.cell.row}`)).toEqual(['3,13']);
    expect(frog.activeBombs).toBe(before);
  });
});

describe('粘膜爆弾の跳ぶ先（原型 updateSlimes）', () => {
  /** 区切り5の粘膜爆弾を、最初の区切りまで進め、着地したマスと残りの区切りを返す。 */
  function hopOnce(seed: number, from: Cell, setup: (world: WorldState, rabbit: PlayerState) => void = () => {}) {
    const { world, frog, rabbit } = arena(seed);
    setup(world, rabbit);
    const actor = new SlimeBombActor(from, frog, 5);
    for (let i = 0; i < 100 && actor.hopsLeft === 5; i += 1) actor.tick(world);
    return { cell: `${actor.cell.col},${actor.cell.row}`, hopsLeft: actor.hopsLeft };
  }

  it('縦横斜めの8方向に跳ぶ（どれも2マス先）', () => {
    const landed = new Set<string>();
    for (let seed = 1; seed <= 200; seed += 1) landed.add(hopOnce(seed, { col: 9, row: 7 }).cell);
    expect([...landed].sort()).toEqual(['11,5', '11,7', '11,9', '7,5', '7,7', '7,9', '9,5', '9,9']);
  });

  it('外周（葱ボンの通り道）には乗らない', () => {
    const landed = new Set<string>();
    for (let seed = 1; seed <= 200; seed += 1) landed.add(hopOnce(seed, { col: 2, row: 3 }).cell);
    expect([...landed].sort()).toEqual(['2,1', '2,5', '4,1', '4,3', '4,5']);
  });

  it('爆弾のあるマスには乗らない', () => {
    const landed = new Set<string>();
    for (let seed = 1; seed <= 200; seed += 1) {
      landed.add(
        hopOnce(seed, { col: 1, row: 1 }, (world, rabbit) => bombWithLongFuse(world, rabbit, { col: 3, row: 1 })).cell,
      );
    }
    expect([...landed].sort()).toEqual(['1,3', '3,3']);
  });

  it('どこにも跳べなければその場に留まり、区切りは減る', () => {
    for (let seed = 1; seed <= 50; seed += 1) {
      const result = hopOnce(seed, { col: 1, row: 1 }, (world, rabbit) => {
        bombWithLongFuse(world, rabbit, { col: 3, row: 1 });
        bombWithLongFuse(world, rabbit, { col: 1, row: 3 });
        bombWithLongFuse(world, rabbit, { col: 3, row: 3 });
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

describe('粘膜爆弾の時間（原型 frogSlime・updateSlimes）', () => {
  it('21 tick 飛んでから、19〜24 tick おきに跳ね、区切りの数より1回少なく跳ねて爆発する', () => {
    // 原型（300 の種）：投げた回から数えて 21 フレーム目に着地し、最初に跳ぶのは 40〜45 フレーム目、
    // 跳ねる間隔は 19〜24 フレーム。6〜8 を引いて、跳ねるのは 5〜7 回。
    const firstHops = new Set<number>();
    const intervals = new Set<number>();
    for (let seed = 1; seed <= 300; seed += 1) {
      const { world, frog } = arena(seed);
      frog.position = centerOf({ col: 9, row: 7 });
      frog.facing = 'right';
      const actor = SlimeBombActor.launch(world, frog);
      const regions = actor.hopsLeft;
      let landedAt: number | null = null;
      let last: number | null = null;
      let hops = 0;
      let done = false;
      for (let t = 1; t <= 300 && !done; t += 1) {
        const before = actor.hopsLeft;
        done = actor.tick(world).done;
        if (landedAt === null && actor.flight === null) landedAt = t;
        if (!done && actor.hopsLeft !== before) {
          hops += 1;
          if (last === null) firstHops.add(t);
          else intervals.add(t - last);
          last = t;
        }
      }
      expect(done, `種 ${seed}`).toBe(true);
      expect(landedAt, `種 ${seed}`).toBe(21);
      expect(hops, `種 ${seed}`).toBe(regions - 1);
    }
    expect([...firstHops].sort((a, b) => a - b)).toEqual([40, 41, 42, 43, 44, 45]);
    expect([...intervals].sort((a, b) => a - b)).toEqual([19, 20, 21, 22, 23, 24]);
  });

  it('爆風に触れたら、飛んでいる間でもすぐ爆発する', () => {
    // 原型：投げて1フレーム後（まだ飛んでいる）に着地するマスへ爆風を置くと、次のフレームで爆発して消える。
    const { world, frog } = arena();
    frog.position = centerOf({ col: 9, row: 7 });
    frog.facing = 'right';
    const actor = SlimeBombActor.launch(world, frog);
    actor.tick(world);
    expect(actor.flight).not.toBeNull();
    expect(actor.cell).toEqual({ col: 12, row: 7 });
    addBlast(world, { col: 12, row: 7 }, 1, false);
    const result = actor.tick(world);
    expect(result.done).toBe(true);
    expect(result.events.some((event) => event.type === 'exploded' && event.owner === frog.id)).toBe(true);
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

describe('舌の長さと時間（原型 startTongue・updateTongue・tongueBurnCheck）', () => {
  /*
   * 原型を画面なしで動かし、技のボタンを押したフレームを 0 として数えた値と比べる。
   * この版の舌は離した tick に始まり、次の tick から進む。ここでは舌の振る舞いを直に作って
   * 1 tick ずつ進め、最初の tick を原型の 1 フレーム目に当てる。
   */
  function frogAt(): { world: WorldState; frog: PlayerState } {
    const { world, frog } = arena();
    frog.position = centerOf({ col: 3, row: 5 });
    frog.facing = 'right';
    return { world, frog };
  }

  function tongueOf(world: WorldState, frog: PlayerState): TongueAction {
    return new TongueAction(cellOf(frog.position), frog.facing);
  }

  /** 終わるまで進め、終わった tick を返す。onTick は各 tick のあとに呼ぶ。 */
  function runTongue(
    world: WorldState,
    frog: PlayerState,
    action: TongueAction,
    onTick: (t: number) => void = () => {},
  ): number {
    for (let t = 1; t <= 300; t += 1) {
      const done = action.tick(world, frog).done;
      onTick(t);
      if (done) return t;
    }
    throw new Error('舌が 300 tick たっても終わらない');
  }

  it('何も無ければ 10 マス伸びて戻り、151 tick 目に終わる（1マスに 7〜8 tick）', () => {
    const { world, frog } = frogAt();
    expect(runTongue(world, frog, tongueOf(world, frog))).toBe(151);
  });

  it('10 マス先のアイテムは取り、11 マス先は取らない', () => {
    for (const [distance, gained] of [[10, 2], [11, 0]] as const) {
      const { world, frog } = frogAt();
      world.items.push({ id: world.ids.take(), cell: { col: 3 + distance, row: 5 }, kind: 'fire' });
      const before = frog.power;
      runTongue(world, frog, tongueOf(world, frog));
      expect(frog.power - before, `${distance} マス先`).toBe(gained);
    }
  });

  it('掴んだアイテムは 23 tick 目に盤面から消え、舌が戻りきった 46 tick 目に効く（3 マス先）', () => {
    const { world, frog } = frogAt();
    world.items.push({ id: world.ids.take(), cell: { col: 6, row: 5 }, kind: 'fire' });
    const before = frog.power;
    let removedAt: number | null = null;
    let appliedAt: number | null = null;
    const end = runTongue(world, frog, tongueOf(world, frog), (t) => {
      if (removedAt === null && world.items.length === 0) removedAt = t;
      if (appliedAt === null && frog.power !== before) appliedAt = t;
    });
    expect({ removedAt, appliedAt, end }).toEqual({ removedAt: 23, appliedAt: 46, end: 46 });
    expect(frog.power - before).toBe(2);
  });

  it('3 マス先のブロックに当たったら引っ込め、38 tick 目に終わる', () => {
    const { world, frog } = frogAt();
    world.board.set({ col: 6, row: 5 }, 'soft');
    expect(runTongue(world, frog, tongueOf(world, frog))).toBe(38);
  });

  it('伸びている舌に爆風が来ると焼き切れる：手前までに短くなり、泣き、10 秒ごとに1マス戻る', () => {
    // 原型：40 フレームで 5 マス伸びた舌の 2 マス目に爆風を置くと、次のフレームで舌が消え、
    // そのラウンドは 1 マスまで・3 秒泣く（動けないのは 181 フレーム）・10 秒たつごとに1マス戻る。
    // 焼けたかを見るのは、その tick の最後（被弾を見たあと。`afterDamage`）。
    const { world, frog } = frogAt();
    const action = tongueOf(world, frog);
    for (let t = 1; t <= 40; t += 1) action.tick(world, frog);
    addBlast(world, { col: 5, row: 5 }, 1, false);
    expect(action.tick(world, frog).done).toBe(false);
    expect(action.afterDamage(world, frog).done).toBe(true);
    expect(tongueReachOf(world, frog)).toBe(1);
    expect(frog.effects.remaining('stun')).toBe(180);

    const sim = new Simulation();
    const reaches: number[] = [];
    let frozen = 0;
    for (let t = 1; t <= 1800; t += 1) {
      sim.step(world, sameForAll(world, press({})));
      if (isFrozen(frog)) frozen += 1;
      reaches.push(tongueReachOf(world, frog));
    }
    expect(frozen).toBeGreaterThanOrEqual(175);
    expect(frozen).toBeLessThanOrEqual(182);
    // 戻るのは焼けてから 600 tick ごと（原型は 600 フレームごと）。
    expect(reaches.indexOf(2) + 1).toBe(600);
    expect(reaches.indexOf(3) + 1).toBe(1200);
    expect(reaches.at(-1)).toBe(4);
  });

  it('焼き切れて泣く長さは、足すのではなく少なくとも 3 秒（原型は残りと 3 秒の長いほう）', () => {
    for (const [before, after] of [[100, 180], [300, 300]] as const) {
      const { world, frog } = frogAt();
      frog.effects.add('stun', tick(before), tick(before));
      const action = tongueOf(world, frog);
      for (let t = 1; t <= 40; t += 1) action.tick(world, frog);
      addBlast(world, { col: 5, row: 5 }, 1, false);
      action.tick(world, frog);
      action.afterDamage(world, frog);
      expect(frog.effects.remaining('stun'), `前に ${before} tick`).toBe(after);
    }
  });

  it('掴んで戻る途中で焼き切れると、掴んでいたものは焦げて効かない', () => {
    const { world, frog } = frogAt();
    world.items.push({ id: world.ids.take(), cell: { col: 7, row: 5 }, kind: 'fire' });
    const before = frog.power;
    const action = tongueOf(world, frog);
    let t = 0;
    while (world.items.length > 0 && t < 60) {
      action.tick(world, frog);
      t += 1;
    }
    expect(t).toBe(31);
    addBlast(world, { col: 4, row: 5 }, 1, false);
    expect(action.tick(world, frog).done).toBe(false);
    expect(action.afterDamage(world, frog).done).toBe(true);
    expect(frog.power - before).toBe(0);
    expect(world.items).toEqual([]);
    expect(tongueReachOf(world, frog)).toBe(0);
  });

  it('根元まで焼けていれば、技のボタンを押しても舌は出ない', () => {
    const { world, frog } = frogAt();
    world.actors.push(new BurntTongueActor(frog.id, 0));
    const sim = new Simulation();
    sim.step(world, onlyFor(world, 0, press({})));
    sim.step(world, onlyFor(world, 0, press({ action: true })));
    sim.step(world, onlyFor(world, 0, press({})));
    expect(frog.action).toBeNull();
  });

  it('焼けた長さは、延長戦に入ると元に戻る（原型もラウンドの始まりと延長戦で戻す）', () => {
    const { world, frog } = frogAt();
    world.actors.push(new BurntTongueActor(frog.id, 2));
    expect(tongueReachOf(world, frog)).toBe(2);
    enterSuddenDeath(world, [0, 1], 'timeUp');
    expect(tongueReachOf(world, frog)).toBe(TONGUE_REACH);
  });

  it('もう一度焼けると、戻るまでの 10 秒を数え直す（原型 tongueBurnCheck の tongueRegen=TONGUE_REGEN）', () => {
    const scar = new BurntTongueActor(0, 3);
    for (let i = 0; i < 300; i += 1) scar.tick();
    scar.burnTo(1);
    let backAt: number | null = null;
    for (let t = 1; t <= 700 && backAt === null; t += 1) {
      scar.tick();
      if (scar.limit === 2) backAt = t;
    }
    // 前の残り（300 tick）では戻らず、焼けてから 600 tick 目に戻る。
    expect(backAt).toBe(600);
  });

  it('伸ばしている途中に焼けた舌が1マス戻れば、そのぶん伸びる（戻っている途中なら伸び直さない）', () => {
    // 原型（legacy_p3_tongue_regen）：舌の長さ 3・4 マス先に fire。12 フレームで1マス戻るなら、
    // 4 マス伸びて掴み、61 フレーム目に終わる。40 フレームで戻るなら（戻っている途中）3 マスで引っ込み、
    // 46 フレーム目に終わってアイテムは残る。
    const scenes = [
      [12, { end: 61, gained: 2, items: 0 }],
      [40, { end: 46, gained: 0, items: 1 }],
    ] as const;
    for (const [regenIn, expected] of scenes) {
      const { world, frog } = frogAt();
      const scar = new BurntTongueActor(frog.id, 3);
      for (let i = 0; i < 600 - regenIn; i += 1) scar.tick();
      world.actors.push(scar);
      world.items.push({ id: world.ids.take(), cell: { col: 7, row: 5 }, kind: 'fire' });
      const before = frog.power;
      const end = runTongue(world, frog, tongueOf(world, frog), () => scar.tick());
      expect({ end, gained: frog.power - before, items: world.items.length }, `${regenIn} tick で戻る`).toEqual(expected);
    }
  });

  it('掴んだ瞬間に知らせるのは掴んだことだけで、拾ったこと（拾った音）は戻りきって効いた tick に知らせる', () => {
    // 原型：掴んだところでは SE.tongueCatch だけ。拾った音（SE.item など）は、戻りきって applyItem したときに鳴る。
    // 戻る途中で焼き切れたら、効かないので拾ったことも知らせない。
    const run = (burn: boolean): string[] => {
      const { world, frog } = frogAt();
      world.items.push({ id: world.ids.take(), cell: { col: 6, row: 5 }, kind: 'fire' });
      const action = tongueOf(world, frog);
      const log: string[] = [];
      for (let t = 1; t <= 60; t += 1) {
        if (burn && t === 25) addBlast(world, { col: 4, row: 5 }, 1, false);
        const advanced = action.tick(world, frog);
        const checked = advanced.done ? { events: [], done: true } : action.afterDamage(world, frog);
        for (const event of [...advanced.events, ...checked.events]) {
          if (event.type === 'techniqueMoment') log.push(`${t}:${event.moment}`);
          if (event.type === 'itemTaken') log.push(`${t}:itemTaken(${event.cell === null ? 'null' : 'cell'})`);
        }
        if (checked.done) break;
      }
      return log;
    };
    expect(run(false)).toEqual(['23:tongueCaught', '46:itemTaken(null)']);
    expect(run(true)).toEqual(['23:tongueCaught']);
  });
});
