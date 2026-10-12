import { describe, expect, it } from 'vitest';

import { startingBonusOf } from '../../src/app/GameSession.js';
import { CPU_LEVELS } from '../../src/ai/CpuLevel.js';
import { CpuInputSource } from '../../src/ai/CpuInputSource.js';
import type { CpuMemory } from '../../src/ai/CpuMemory.js';
import { ChargeAction } from '../../src/domain/abilities/elephant/ChargeAction.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
import { ScatterActor } from '../../src/domain/abilities/rabbit/ScatterActor.js';
import { centerOf, type Cell } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { IDLE_INPUT } from '../../src/domain/input/PlayerInput.js';
import { placeBombAt } from '../../src/domain/mutations/bombs.js';
import { itemEffectTicks } from '../../src/domain/rules/items.js';
import type { PlayerState } from '../../src/domain/state/PlayerState.js';
import { createWorld, hashWorld, type WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { clearBoard, makeWorld, onlyFor, press, sameForAll } from '../helpers.js';

/*
 * 技のボタンと「勝手に設置」を、原型（legacy/animal-bomber.html の humanUpdate・doAction・doSpecial・
 * update）に合わせる。期待値は原型を画面なしで動かして測った値。
 *
 * 原型は、技のボタンを押した瞬間に通常技を出し、押し続けてしきい値に届いた瞬間にとくぎを出す。
 * どちらも、泣いている・落とし穴にはまっている（isFrozen）・舌を伸ばしている間は何もせずに帰り、
 * その押し方の分は捨てる。
 * しきい値は、原型は 1/60 秒を小数で足していくので、0.5 秒が 31 フレーム目・1.5 秒が 91 フレーム目に
 * なる。この版は tick で数えるので 30・90 tick 目（1つ早い）。ほかの値は原型と同じ。
 */

function arena(animals: [string, string]): WorldState {
  const world = makeWorld(2468, animals);
  clearBoard(world);
  world.items = [];
  return world;
}

function place(player: PlayerState, cell: Cell): void {
  player.position = centerOf(cell);
}

/** 0番を (3,7) 右向き、1番を (19,13) に置き、0番にチキン1つ。ラウンドの途中の、何も押していない状態にする。 */
function duel(animal: string, other = 'frog'): { world: WorldState; me: PlayerState; foe: PlayerState; sim: Simulation } {
  const world = arena([animal, other]);
  const [me, foe] = world.players as [PlayerState, PlayerState];
  place(me, { col: 3, row: 7 });
  me.facing = 'right';
  place(foe, { col: 19, row: 13 });
  me.specialCharges = 1;
  me.actionFired = false;
  return { world, me, foe, sim: new Simulation() };
}

/** 0番が技のボタンを押し続けるあいだ、1 tick ごとに `watch` を呼ぶ（t は押した tick を 1 と数える）。 */
function holdFor(world: WorldState, sim: Simulation, ticks: number, watch: (t: number, events: SimEvent[]) => void): void {
  for (let t = 1; t <= ticks; t += 1) watch(t, sim.step(world, onlyFor(world, 0, press({ action: true }))));
}

const scatteredCells = (world: WorldState): string[] =>
  world.items.filter((item) => item.scatteredBy !== undefined).map((item) => `${item.cell.col},${item.cell.row}`);

describe('押した瞬間の通常技と、しきい値のとくぎ（原型 humanUpdate）', () => {
  it('うさぎ：押した tick に跳び、30 tick 目に跳んだ先で撒く（原型 1・31 フレーム目）', () => {
    const { world, me: rabbit, sim } = duel('rabbit');
    let hopAt: number | null = null;
    let scatterAt: number | null = null;
    holdFor(world, sim, 60, (t) => {
      if (hopAt === null && rabbit.position.x !== 3.5) hopAt = t;
      if (scatterAt === null && world.actors.some((actor) => actor instanceof ScatterActor)) scatterAt = t;
    });
    expect({ hopAt, scatterAt, x: rabbit.position.x, charges: rabbit.specialCharges }).toEqual({
      hopAt: 1,
      scatterAt: 30,
      x: 5.5,
      charges: 0,
    });
    expect(scatteredCells(world)).toContain('5,7');
  });

  it('ぞう：押した tick に鼻水で2マス先の爆弾を消し、90 tick 目に突進する（原型 1・91 フレーム目）', () => {
    const { world, me: elephant, foe, sim } = duel('elephant');
    placeBombAt(world, foe, { col: 5, row: 7 })!.fuse = tick(999);
    let dousedAt: number | null = null;
    let chargeAt: number | null = null;
    holdFor(world, sim, 120, (t) => {
      if (dousedAt === null && world.bombs.length === 0) dousedAt = t;
      if (chargeAt === null && elephant.action?.kind === 'charge') chargeAt = t;
    });
    expect({ dousedAt, chargeAt }).toEqual({ dousedAt: 1, chargeAt: 90 });
  });

  it('きつね：押した tick に一列に置き、30 tick 目に跳ぶ（原型 1・31 フレーム目）', () => {
    const { world, me: fox, sim } = duel('fox');
    let lineAt: number | null = null;
    let cells: string[] = [];
    let leapAt: number | null = null;
    holdFor(world, sim, 60, (t) => {
      if (lineAt === null && world.bombs.length > 0) {
        lineAt = t;
        cells = world.bombs.map((bomb) => `${bomb.cell.col},${bomb.cell.row}`);
      }
      if (leapAt === null && fox.effects.has('leap')) leapAt = t;
    });
    expect({ lineAt, cells, leapAt }).toEqual({ lineAt: 1, cells: ['4,7', '5,7'], leapAt: 30 });
  });

  it('かえる：押した tick に舌が出る。開けた通路では舌の最中にしきい値が来て、とくぎは出ずチキンも減らない', () => {
    // 原型：舌は 60 フレームたっても戻らず、粘膜爆弾は出ない。actFired は立つ。
    const { world, me: frog, sim } = duel('frog', 'fox');
    let tongueAt: number | null = null;
    const tongues = new Set<unknown>();
    holdFor(world, sim, 60, (t) => {
      if (tongueAt === null && frog.action?.kind === 'tongue') tongueAt = t;
      if (frog.action !== null) tongues.add(frog.action);
    });
    expect(tongueAt).toBe(1);
    // 押し続けても舌は伸ばし直さない（ボタンを受け付けない）。
    expect(tongues.size).toBe(1);
    expect(world.actors.some((actor) => actor.kind === 'slime')).toBe(false);
    expect([frog.specialCharges, frog.actionFired]).toEqual([1, true]);
  });

  it('かえる：壁を向いて押すと、舌がしきい値より前に戻り、30 tick 目に粘膜爆弾を投げる（原型 17 フレーム目に戻り、31 で投げる）', () => {
    const { world, me: frog, sim } = duel('frog', 'fox');
    place(frog, { col: 1, row: 1 });
    frog.facing = 'up';
    let tongueEnd: number | null = null;
    let slimeAt: number | null = null;
    holdFor(world, sim, 60, (t) => {
      if (tongueEnd === null && t > 1 && frog.action === null) tongueEnd = t;
      if (slimeAt === null && world.actors.some((actor) => actor.kind === 'slime')) slimeAt = t;
    });
    expect({ tongueEnd, slimeAt, charges: frog.specialCharges }).toEqual({ tongueEnd: 17, slimeAt: 30, charges: 0 });
  });

  it('ラウンドの始まりから押していると、離すまで通常技もとくぎも出ない。離して押し直せば押した tick に出る', () => {
    // 原型：60 フレーム押し続けても跳ばず撒かず、61 で離して 62 で押すと 62 に跳ぶ。
    const world = createWorld({ seed: 2468, animals: ['rabbit', 'frog'], bonusOf: startingBonusOf });
    clearBoard(world);
    world.items = [];
    const [rabbit, frog] = world.players as [PlayerState, PlayerState];
    place(rabbit, { col: 3, row: 7 });
    rabbit.facing = 'right';
    place(frog, { col: 19, row: 13 });
    rabbit.specialCharges = 1;
    const sim = new Simulation();
    let movedAt: number | null = null;
    for (let t = 1; t <= 70; t += 1) {
      sim.step(world, onlyFor(world, 0, press({ action: t <= 60 || t >= 62 })));
      if (movedAt === null && rabbit.position.x !== 3.5) movedAt = t;
    }
    expect(movedAt).toBe(62);
    expect(world.actors.some((actor) => actor instanceof ScatterActor)).toBe(false);
  });
});

describe('振る舞いの最中の技のボタン（原型は舌の間だけボタンを止める）', () => {
  it('突進の最中に押すと、押した tick に鼻水が出る（突進は続く）', () => {
    // 原型：2 フレーム進んだあと (3.891667) に押すと、その tick に 4.0875 まで進んでから (6,7) の爆弾を消す。
    const { world, me: elephant, foe, sim } = duel('elephant');
    elephant.action = new ChargeAction('right');
    sim.step(world, sameForAll(world, press({})));
    sim.step(world, sameForAll(world, press({})));
    expect(elephant.position.x).toBeCloseTo(3.891667, 5);
    placeBombAt(world, foe, { col: 6, row: 7 })!.fuse = tick(999);
    sim.step(world, onlyFor(world, 0, press({ action: true })));
    expect(elephant.position.x).toBeCloseTo(4.0875, 5);
    expect(world.bombs).toEqual([]);
    expect(elephant.action?.kind).toBe('charge');
    expect(elephant.abilityCooldown).toBe(300);
  });

  it('突進の最中にしきい値が来ると、突進が最初からやり直しになり、抱えていた悪いアイテムは撒かれずに消える', () => {
    // 原型：85 フレーム押したところで突進を始め、91 フレーム目にやり直し（残り 5 秒・抱えた物は空・アイテム 0）。
    const run = (restart: boolean): { restartAt: number | null; items: string[]; spat: number } => {
      const { world, me: elephant, sim } = duel('elephant');
      elephant.specialCharges = 0;
      elephant.abilityCooldown = tick(9999); // 鼻水は出ないようにしておく
      world.items.push({ id: world.ids.take(), cell: { col: 4, row: 7 }, kind: 'onion' });
      const events: SimEvent[] = [];
      let first: ChargeAction | null = null;
      let restartAt: number | null = null;
      holdFor(world, sim, 400, (t, stepEvents) => {
        events.push(...stepEvents);
        if (t === 84) {
          first = new ChargeAction('right');
          elephant.action = first;
          if (restart) elephant.specialCharges = 1;
        }
        if (restartAt === null && first !== null && elephant.action !== null && elephant.action !== first) restartAt = t;
      });
      return {
        restartAt,
        items: world.items.map((item) => `${item.kind}@${item.cell.col},${item.cell.row}`),
        spat: events.filter((e) => e.type === 'itemDropped').length,
      };
    };
    const control = run(false);
    expect(control.restartAt).toBeNull();
    expect(control.spat).toBe(1);
    expect(run(true)).toEqual({ restartAt: 90, items: [], spat: 0 });
  });

  it('掘っている最中に押すと、チキンだけ減り、掘るのは続く（掘り終わる tick は変わらない）', () => {
    // 原型：もう1つチキンを持たせて押し直すと、チキンは消え、掘り終わりは押さないときと同じ 92 フレーム目。
    const run = (pressAgain: boolean): { doneAt: number | null; charges: number; pits: number } => {
      const { world, me: mole, sim } = duel('mole');
      sim.step(world, onlyFor(world, 0, press({ action: true })));
      expect([mole.action?.kind, mole.specialCharges]).toEqual(['dig', 0]);
      let doneAt: number | null = null;
      for (let t = 2; t <= 120 && doneAt === null; t += 1) {
        if (t === 10) mole.specialCharges = 1;
        sim.step(world, onlyFor(world, 0, press({ action: pressAgain && t >= 11 })));
        if (mole.action === null) doneAt = t;
      }
      return { doneAt, charges: mole.specialCharges, pits: world.actors.filter((a) => a.kind === 'pit').length };
    };
    const plain = run(false);
    expect(plain.charges).toBe(1);
    expect(run(true)).toEqual({ doneAt: plain.doneAt, charges: 0, pits: 1 });
  });

  it('振る舞いが終わった tick に押せば、その tick のうちに次の技が出る', () => {
    // 原型：2 マス先を掴んで戻る舌は 32 フレーム目に戻り、そのフレームに押すと長さ 0 の舌が出る。
    const run = (pressAt: number): { endAt: number | null; tongue: unknown } => {
      const { world, me: frog, sim } = duel('frog', 'fox');
      frog.specialCharges = 0;
      world.items.push({ id: world.ids.take(), cell: { col: 5, row: 7 }, kind: 'fire' });
      sim.step(world, onlyFor(world, 0, press({ action: true })));
      const first = frog.action;
      for (let t = 2; t <= 120; t += 1) {
        sim.step(world, onlyFor(world, 0, press({ action: t === pressAt })));
        if (frog.action !== first) return { endAt: t, tongue: frog.action };
      }
      return { endAt: null, tongue: null };
    };
    const plain = run(-1);
    expect(plain).toEqual({ endAt: 32, tongue: null });
    const pressed = run(32);
    expect(pressed.endAt).toBe(32);
    expect((pressed.tongue as { kind: string } | null)?.kind).toBe('tongue');
  });
});

interface RabbitScene {
  readonly pressAt: number;
  readonly releaseAt: number;
  readonly stunAt: number;
  readonly stunTicks: number;
}

/** うさぎ（0番）を (5,5) 右向きに置き、チキン1つ。決めた tick に押す・離す・泣かせる。 */
function rabbitScene({ pressAt, releaseAt, stunAt, stunTicks }: RabbitScene) {
  const world = arena(['rabbit', 'frog']);
  const [rabbit, frog] = world.players as [PlayerState, PlayerState];
  place(rabbit, { col: 5, row: 5 });
  rabbit.facing = 'right';
  place(frog, { col: 19, row: 13 });
  rabbit.specialCharges = 1;
  const sim = new Simulation();
  let hopAt: number | null = null;
  const x0 = rabbit.position.x;
  for (let t = 0; t < 260; t += 1) {
    if (t === stunAt) rabbit.effects.add('stun', tick(stunTicks), tick(stunTicks * 2));
    const before = rabbit.position.x;
    sim.step(world, onlyFor(world, 0, press({ action: t >= pressAt && t < releaseAt })));
    if (hopAt === null && rabbit.position.x !== before) hopAt = t;
  }
  return {
    hopAt,
    moved: rabbit.position.x - x0,
    charges: rabbit.specialCharges,
    scattered: world.items.filter((item) => item.scatteredBy !== undefined).length,
  };
}

describe('泣いている・はまっている間の技のボタン（原型 doAction・doSpecial の isFrozen）', () => {
  it('泣いている間に押し始めた押し方は、泣き終わってから離しても何も出ない', () => {
    // 原型：押した瞬間に通常技を出そうとして isFrozen で帰る。離しても何も起きない。
    const result = rabbitScene({ pressAt: 50, releaseAt: 70, stunAt: 0, stunTicks: 60 });
    expect(result).toMatchObject({ hopAt: null, moved: 0, charges: 1, scattered: 0 });
  });

  it('押した tick に跳び、そのあと泣いている間にしきい値に届いたら、とくぎは出ずチキンも減らない', () => {
    // 原型：泣く前に跳ぶ。doSpecial は isFrozen で帰る（actFired は立つので、その押し方のとくぎはそれきり）。
    const result = rabbitScene({ pressAt: 10, releaseAt: 50, stunAt: 15, stunTicks: 120 });
    expect(result).toMatchObject({ hopAt: 10, charges: 1, scattered: 0 });
  });

  it('泣いている間に押し始めても、泣き終わってからしきい値に届けば、とくぎは出る（跳ばない）', () => {
    // 原型：とくぎを出すかは、しきい値に届いた瞬間に動けるかだけで決まる（20 フレーム泣いて 31 で撒く。
    // 40 フレーム泣くと、しきい値の時点で泣いていて撒かず、チキンも残る）。
    const result = rabbitScene({ pressAt: 5, releaseAt: 60, stunAt: 0, stunTicks: 18 });
    expect(result).toMatchObject({ hopAt: null, charges: 0 });
    expect(result.scattered).toBeGreaterThan(0);
    expect(rabbitScene({ pressAt: 1, releaseAt: 60, stunAt: 0, stunTicks: 40 })).toMatchObject({
      hopAt: null,
      charges: 1,
      scattered: 0,
    });
  });

  it('とくぎを出し終えたかは状態の要約に混ざる（記録から戻しても同じ判定になる）', () => {
    const a = arena(['rabbit', 'frog']);
    const b = arena(['rabbit', 'frog']);
    b.players[0]!.actionFired = !b.players[0]!.actionFired;
    expect(hashWorld(a)).not.toBe(hashWorld(b));
  });

  it('対照：泣いていなければ、押した tick に跳び、押し続けると撒く', () => {
    expect(rabbitScene({ pressAt: 10, releaseAt: 20, stunAt: -1, stunTicks: 0 }).hopAt).toBe(10);
    const held = rabbitScene({ pressAt: 10, releaseAt: 60, stunAt: -1, stunTicks: 0 });
    expect(held).toMatchObject({ hopAt: 10, charges: 0 });
    expect(held.scattered).toBeGreaterThan(0);
  });

  for (const animal of ['rabbit', 'elephant', 'fox', 'frog', 'mole']) {
    for (const effect of ['stun', 'pitfall'] as const) {
      it(`${animal}：${effect === 'stun' ? '泣いている' : 'はまっている'}間は、押して離しても長押ししても技が出ない`, () => {
        const world = arena([animal, 'rabbit']);
        const [player, other] = world.players as [PlayerState, PlayerState];
        place(player, { col: 5, row: 5 });
        player.facing = 'right';
        place(other, { col: 19, row: 13 });
        player.specialCharges = 1;
        world.items.push({ id: world.ids.take(), cell: { col: 8, row: 5 }, kind: 'fire' });
        player.effects.add(effect, tick(240), tick(240));
        const sim = new Simulation();
        const events: SimEvent[] = [];
        const before = { ...player.position };
        events.push(...sim.step(world, sameForAll(world, press({}))));
        events.push(...sim.step(world, onlyFor(world, 0, press({ action: true }))));
        events.push(...sim.step(world, sameForAll(world, press({}))));
        for (let i = 0; i < abilityOf(animal).holdTicks + 2; i += 1) {
          events.push(...sim.step(world, onlyFor(world, 0, press({ action: true }))));
        }
        events.push(...sim.step(world, sameForAll(world, press({}))));
        expect(events.filter((e) => e.type === 'techniqueUsed')).toEqual([]);
        expect(player.action).toBeNull();
        expect(player.specialCharges).toBe(1);
        expect(player.position).toEqual(before);
        expect(world.bombs).toEqual([]);
        expect(world.actors).toEqual([]);
      });
    }
  }
});

describe('技を進める・勝手に設置・技を始める、の順（原型 update の効果のループと入力のループ）', () => {
  it('技を始める tick に拍が来たら、置いてから技を始める（原型は (1,1) に置いてから舌）', () => {
    const world = arena(['frog', 'rabbit']);
    const [frog, rabbit] = world.players as [PlayerState, PlayerState];
    place(frog, { col: 1, row: 1 });
    frog.facing = 'right';
    place(rabbit, { col: 19, row: 13 });
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    // 押す tick（通常技が出る tick）に、最初の拍が来るようにする。
    frog.effects.add('autobomb', itemEffectTicks(4), itemEffectTicks(12));
    sim.step(world, onlyFor(world, 0, press({ action: true })));
    expect(world.bombs.map((bomb) => [bomb.cell.col, bomb.cell.row, bomb.owner])).toEqual([[1, 1, 0]]);
    expect(frog.action?.kind).toBe('tongue');
  });

  it('番号の大きいプレイヤーの突進が拍のプレイヤーにぶつかると、置いた爆弾を同じ tick に起爆する', () => {
    // 原型：1人ずつ「技を進める → 勝手に設置」を回すので、1P の拍が 2P の突進より先。
    const world = arena(['rabbit', 'elephant']);
    const [rabbit, elephant] = world.players as [PlayerState, PlayerState];
    rabbit.position = { x: 3.5, y: 1.5 };
    elephant.position = { x: 4.3, y: 1.5 };
    elephant.action = new ChargeAction('left');
    rabbit.effects.add('autobomb', itemEffectTicks(4), itemEffectTicks(12));
    new Simulation().step(world, sameForAll(world, press({})));
    expect(world.bombs).toEqual([]);
    expect(world.blasts.map((blast) => `${blast.cell.col},${blast.cell.row}`)).toEqual([
      '3,1',
      '4,1',
      '2,1',
      '3,2',
    ]);
    expect(rabbit.position.x).toBeCloseTo(2.4, 5);
  });

  it('振る舞いが終わった tick に押せば、終わった振る舞いの後始末のあとに次の技が出る', () => {
    const world = arena(['frog', 'rabbit']);
    const [frog, rabbit] = world.players as [PlayerState, PlayerState];
    place(frog, { col: 1, row: 1 });
    frog.facing = 'right';
    place(rabbit, { col: 19, row: 13 });
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    let finished = 0;
    frog.action = {
      kind: 'probe',
      drivesMovement: true,
      damageCap: null,
      untouchable: false,
      canPlaceBomb: false,
      blocksButtons: true,
      sweepsItems: false,
      tick: () => ({ events: [], done: true }),
      finish: () => {
        finished += 1;
        return [];
      },
    };
    const events = sim.step(world, onlyFor(world, 0, press({ action: true })));
    expect(finished).toBe(1);
    expect(events.filter((e) => e.type === 'techniqueUsed')).toEqual([{ type: 'techniqueUsed', player: 0, special: false }]);
    expect(frog.action?.kind).toBe('tongue');
  });

  it('番号の小さいプレイヤーの突進が拍のプレイヤーにぶつかると、押しのけたあとのマスに置く（起爆しない）', () => {
    const world = arena(['elephant', 'rabbit']);
    const [elephant, rabbit] = world.players as [PlayerState, PlayerState];
    rabbit.position = { x: 3.5, y: 1.5 };
    elephant.position = { x: 4.3, y: 1.5 };
    elephant.action = new ChargeAction('left');
    rabbit.effects.add('autobomb', itemEffectTicks(4), itemEffectTicks(12));
    new Simulation().step(world, sameForAll(world, press({})));
    expect(world.bombs.map((bomb) => [bomb.cell.col, bomb.cell.row, bomb.owner])).toEqual([[2, 1, 1]]);
    expect(world.blasts).toEqual([]);
  });
});

describe('CPU は泣いている・はまっている間は何もしない（原型 cpuUpdate の isFrozen）', () => {
  for (const effect of ['stun', 'pitfall'] as const) {
    it(`${effect === 'stun' ? '泣いている' : 'はまっている'}間は何も押さず、考え直しもしない。動けるようになれば押す`, () => {
      // 射線に相手がいて、とくぎも使える場面。動けない間は、爆弾もとくぎも押さず、計画も立てない。
      const world = arena(['rabbit', 'frog']);
      const [rabbit, frog] = world.players as [PlayerState, PlayerState];
      place(rabbit, { col: 5, row: 5 });
      place(frog, { col: 7, row: 5 });
      rabbit.specialCharges = 1;
      rabbit.effects.add(effect, tick(30), tick(30));
      const source = new CpuInputSource(0, CPU_LEVELS.oni, 1);
      const sim = new Simulation();
      const inputs = [];
      for (let t = 0; t < 30; t += 1) {
        const input = source.next(world);
        inputs.push(input);
        sim.step(world, new Map([[0, input], [1, IDLE_INPUT]]));
      }
      expect(inputs).toEqual(inputs.map(() => IDLE_INPUT));
      expect((source.memory as CpuMemory).mode).toBe('idle');
      const after = source.next(world);
      expect(after.bomb || after.special).toBe(true);
    });
  }
});
