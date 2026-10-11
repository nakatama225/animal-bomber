import { describe, expect, it } from 'vitest';

import { ButtonMacro } from '../../src/ai/ButtonMacro.js';
import { CPU_LEVELS } from '../../src/ai/CpuLevel.js';
import { CpuInputSource } from '../../src/ai/CpuInputSource.js';
import type { CpuMemory } from '../../src/ai/CpuMemory.js';
import { ChargeAction } from '../../src/domain/abilities/elephant/ChargeAction.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
import { centerOf, type Cell } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { IDLE_INPUT } from '../../src/domain/input/PlayerInput.js';
import { itemEffectTicks } from '../../src/domain/rules/items.js';
import type { PlayerState } from '../../src/domain/state/PlayerState.js';
import { hashWorld, type WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { clearBoard, makeWorld, onlyFor, press, sameForAll } from '../helpers.js';

/*
 * 技のボタンと「勝手に設置」を、原型（legacy/animal-bomber.html の humanUpdate・doAction・doSpecial・
 * update）に合わせる。期待値は原型を画面なしで動かして測った値。
 *
 * 原型は、技のボタンを押した瞬間に通常技を出し、押し続けてしきい値に届いた瞬間にとくぎを出す。
 * どちらも、泣いている・落とし穴にはまっている（isFrozen）なら何もせずに帰り、その押し方の分は捨てる。
 * この版は離した瞬間に通常技を出すので、押した瞬間の確かめを2つに分けて写している
 * （押し始めに動けなかった押し方は通常技にしない・離したときに動けなければ通常技にしない）。
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
  it('泣いている間に押し始めた押し方は、泣き終わってから離しても通常技にならない', () => {
    // 原型：押した瞬間に通常技を出そうとして isFrozen で帰る。離しても何も起きない。
    const result = rabbitScene({ pressAt: 50, releaseAt: 70, stunAt: 0, stunTicks: 60 });
    expect(result).toMatchObject({ hopAt: null, moved: 0, charges: 1, scattered: 0 });
  });

  it('泣いている間にしきい値に届いたら、とくぎは出ずチキンも減らない', () => {
    // 原型：doSpecial が isFrozen で帰る（actFired は立つので、その押し方のとくぎはそれきり）。
    // ⚠️ 原型は押し始め（泣く前）に通常技も出す（跳ぶ）。この版は長押しを離しても通常技にしないので跳ばない。
    const result = rabbitScene({ pressAt: 10, releaseAt: 50, stunAt: 15, stunTicks: 120 });
    expect(result).toMatchObject({ charges: 1, scattered: 0 });
    expect(result.hopAt).toBeNull();
  });

  it('泣いている間に離したら、通常技は出ない', () => {
    // ⚠️ 原型は押した瞬間（泣く前）に跳ぶ。この版は離した瞬間に出すので、泣いている間に
    // 出すことになる。泣いたまま跳んで逃げられないよう、出さないと決めた。
    const result = rabbitScene({ pressAt: 10, releaseAt: 20, stunAt: 15, stunTicks: 120 });
    expect(result.hopAt).toBeNull();
  });

  it('泣いている間に押し始めても、泣き終わってからしきい値に届けば、とくぎは出る', () => {
    // 原型：とくぎを出すかは、しきい値に届いた瞬間に動けるかだけで決まる。
    const result = rabbitScene({ pressAt: 5, releaseAt: 60, stunAt: 0, stunTicks: 18 });
    expect(result).toMatchObject({ hopAt: null, charges: 0 });
    expect(result.scattered).toBeGreaterThan(0);
  });

  it('押し始めに動けなかったことは状態の要約に混ざる（記録から戻しても同じ判定になる）', () => {
    const a = arena(['rabbit', 'frog']);
    const b = arena(['rabbit', 'frog']);
    b.players[0]!.tapVoided = true;
    expect(hashWorld(a)).not.toBe(hashWorld(b));
  });

  it('対照：泣いていなければ、押して離すと跳び、長押しで撒く', () => {
    expect(rabbitScene({ pressAt: 10, releaseAt: 20, stunAt: -1, stunTicks: 0 }).hopAt).toBe(20);
    const held = rabbitScene({ pressAt: 10, releaseAt: 60, stunAt: -1, stunTicks: 0 });
    expect(held).toMatchObject({ hopAt: null, charges: 0 });
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
    sim.step(world, onlyFor(world, 0, press({ action: true })));
    // 離す tick（通常技が出る tick）に、最初の拍が来るようにする。
    frog.effects.add('autobomb', itemEffectTicks(4), itemEffectTicks(12));
    sim.step(world, sameForAll(world, press({})));
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

  it('振る舞いが終わった tick には、ボタンを離しても新しい技を始めない（1 tick あと）', () => {
    // 原型は同じフレームのうちに始められる。この版は1 tick 待つ形のまま（ActionSystem の説明）。
    const world = arena(['frog', 'rabbit']);
    const [frog, rabbit] = world.players as [PlayerState, PlayerState];
    place(frog, { col: 1, row: 1 });
    frog.facing = 'right';
    place(rabbit, { col: 19, row: 13 });
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    sim.step(world, onlyFor(world, 0, press({ action: true })));
    let finished = 0;
    frog.action = {
      kind: 'probe',
      drivesMovement: true,
      damageCap: null,
      untouchable: false,
      canPlaceBomb: false,
      sweepsItems: false,
      tick: () => ({ events: [], done: true }),
      finish: () => {
        finished += 1;
        return [];
      },
    };
    const events = sim.step(world, sameForAll(world, press({})));
    expect(finished).toBe(1);
    expect(events.filter((e) => e.type === 'techniqueUsed')).toEqual([]);
    expect(frog.action).toBeNull();
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
    it(`長押しの途中で${effect === 'stun' ? '泣く' : 'はまる'}と、ボタンを離して手順を捨てる`, () => {
      const world = arena(['rabbit', 'frog']);
      const [rabbit, frog] = world.players as [PlayerState, PlayerState];
      place(rabbit, { col: 5, row: 5 });
      place(frog, { col: 19, row: 13 });
      rabbit.actionHeld = tick(0);
      const source = new CpuInputSource(0, CPU_LEVELS.oni, 1);
      const sim = new Simulation();
      sim.step(world, new Map([[0, source.next(world)], [1, IDLE_INPUT]]));
      const memory = source.memory as CpuMemory;
      memory.macro = ButtonMacro.hold(abilityOf('rabbit').holdTicks, true);
      sim.step(world, new Map([[0, source.next(world)], [1, IDLE_INPUT]]));
      expect(rabbit.actionHeld).toBeGreaterThan(0);

      rabbit.effects.add(effect, tick(120), tick(120));
      expect(source.next(world)).toEqual(IDLE_INPUT);
      expect(source.memory.macro).toBeNull();
    });
  }
});
