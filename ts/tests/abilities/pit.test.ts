import { describe, expect, it } from 'vitest';

import { ChargeAction } from '../../src/domain/abilities/elephant/ChargeAction.js';
import { PitActor } from '../../src/domain/abilities/mole/PitAction.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
import { centerOf, type Cell } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { placeBomb } from '../../src/domain/mutations/bombs.js';
import { applyItem } from '../../src/domain/mutations/items.js';
import { itemEffectTicks } from '../../src/domain/rules/items.js';
import { isFrozen, type PlayerState } from '../../src/domain/state/PlayerState.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { advance, clearBoard, grantSpecial, makeWorld, onlyFor, press, sameForAll } from '../helpers.js';

/*
 * 落とし穴を原型（legacy/animal-bomber.html の startDigPit・updateDigging・pitfallCheck）に合わせる。
 * 期待値は原型を画面なしで動かして測った値。
 * tick の終わりに止まっているかを数えると、原型 181 フレーム・この版 179 tick で2つ違う。
 * 1つは原型の秒の小数の残り（1/60 秒ずつ 3 秒を引くと、181 回目で 0 を切る）。もう1つは減らす位置で、
 * この版は動けない最後の tick の終わりに状態を消すので、その tick が数に入らない。
 * 動けるようになるのは原型 181 フレーム目・この版 180 tick 目。幅を持たせて比べる。
 */

/** 盤面を空にした世界。0番と1番を指定の動物にし、アイテムを片付ける。 */
function arena(animals: [string, string]): WorldState {
  const world = makeWorld(2468, animals);
  clearBoard(world);
  world.items = [];
  return world;
}

/**
 * 1人に技のボタンを押させて、とくぎを出す。もぐらは通常技が無いので、押した瞬間にとくぎが出る
 * （原型の doAction）。押した tick で終わる（離す tick は呼んだ側が進める）。
 */
function pressSpecial(world: WorldState, who: 0 | 1, sim: Simulation): void {
  sim.step(world, onlyFor(world, who, press({})));
  sim.step(world, onlyFor(world, who, press({ action: true })));
}

function pitCells(world: WorldState): string[] {
  return world.actors
    .filter((actor): actor is PitActor => actor instanceof PitActor)
    .map((pit) => `${pit.cell.col},${pit.cell.row}`);
}

/** n tick 進め、そのうち動けなかった tick を数える。onTick は各 tick の前に呼ぶ。 */
function countFrozen(
  world: WorldState,
  player: PlayerState,
  ticks: number,
  onTick: (t: number) => void = () => {},
): number {
  const sim = new Simulation();
  let frozen = 0;
  for (let t = 0; t < ticks; t += 1) {
    onTick(t);
    sim.step(world, sameForAll(world, press({})));
    if (isFrozen(player)) frozen += 1;
  }
  return frozen;
}

function place(player: PlayerState, cell: Cell): void {
  player.position = centerOf(cell);
}

describe('掘る（原型 startDigPit・updateDigging）', () => {
  it('同じマスを2回掘っても穴は1つで、踏んだ相手が動けないのは1回ぶん（2回目もチキンは減る）', () => {
    // 原型：2回目の startDigPit は「すでに穴がある」で掘らず、チキンは減る。踏んだうさぎは 181 フレーム。
    const world = arena(['mole', 'rabbit']);
    const [mole, rabbit] = world.players as [PlayerState, PlayerState];
    place(mole, { col: 5, row: 5 });
    place(rabbit, { col: 19, row: 13 });
    grantSpecial(mole, 2);
    const sim = new Simulation();
    pressSpecial(world, 0, sim);
    advance(world, onlyFor(world, 0, press({})), 100, sim);
    pressSpecial(world, 0, sim);
    // 2回目は掘り始めない（原型も掘り始めない）。掘り終わりの確かめだけに任せると、
    // 何も生まない「掘る」で 90 tick 動けなくなる。
    expect(mole.action).toBeNull();
    advance(world, onlyFor(world, 0, press({})), 100, sim);
    expect(mole.specialCharges).toBe(0);
    expect(pitCells(world)).toEqual(['5,5']);

    place(mole, { col: 1, row: 1 });
    place(rabbit, { col: 5, row: 5 });
    const frozen = countFrozen(world, rabbit, 400);
    expect(frozen).toBeGreaterThanOrEqual(175);
    expect(frozen).toBeLessThanOrEqual(182);
  });

  it('壊せるブロックの中では掘らない（チキンは減る）', () => {
    const world = arena(['mole', 'rabbit']);
    const [mole, rabbit] = world.players as [PlayerState, PlayerState];
    place(mole, { col: 5, row: 5 });
    place(rabbit, { col: 19, row: 13 });
    world.board.set({ col: 5, row: 5 }, 'soft');
    grantSpecial(mole, 1);
    const sim = new Simulation();
    pressSpecial(world, 0, sim);
    expect(mole.action).toBeNull();
    advance(world, onlyFor(world, 0, press({})), 100, sim);
    expect(mole.specialCharges).toBe(0);
    expect(pitCells(world)).toEqual([]);
  });

  it('自分の爆弾の上では掘らない（チキンは減る）', () => {
    const world = arena(['mole', 'rabbit']);
    const [mole, rabbit] = world.players as [PlayerState, PlayerState];
    place(mole, { col: 5, row: 5 });
    place(rabbit, { col: 19, row: 13 });
    const bomb = placeBomb(world, mole);
    if (bomb === undefined) throw new Error('爆弾を置けなかった');
    bomb.fuse = tick(9999);
    grantSpecial(mole, 1);
    const sim = new Simulation();
    pressSpecial(world, 0, sim);
    expect(mole.action).toBeNull();
    advance(world, onlyFor(world, 0, press({})), 100, sim);
    expect(mole.specialCharges).toBe(0);
    expect(pitCells(world)).toEqual([]);
  });

  it('掘っている途中に押し出されたらやめ、穴はできない', () => {
    const world = arena(['mole', 'rabbit']);
    const [mole, rabbit] = world.players as [PlayerState, PlayerState];
    place(mole, { col: 5, row: 5 });
    place(rabbit, { col: 19, row: 13 });
    grantSpecial(mole, 1);
    const sim = new Simulation();
    pressSpecial(world, 0, sim);
    expect(mole.action?.kind).toBe('dig');
    advance(world, onlyFor(world, 0, press({})), 30, sim);
    place(mole, { col: 7, row: 5 });
    advance(world, onlyFor(world, 0, press({})), 1, sim);
    expect(mole.action).toBeNull();
    advance(world, onlyFor(world, 0, press({})), 100, sim);
    expect(pitCells(world)).toEqual([]);
  });

  it('掘っている途中に同じマスへ爆弾を置かれても、掘り終わりに穴ができ、爆発のあとも残る', () => {
    // 原型の掘り終わり（updateDigging）が確かめ直すのはマスと穴だけで、爆弾は見ない。
    // 原型の答え（掘り始めて 5・30・85 フレーム目に置く）：どれも掘り終わりに (5,5) に穴が1つ、爆発のあとも残り、踏むと落ちる。
    for (const at of [5, 30, 85]) {
      const world = arena(['mole', 'rabbit']);
      const [mole, rabbit] = world.players as [PlayerState, PlayerState];
      place(mole, { col: 5, row: 5 });
      place(rabbit, { col: 19, row: 13 });
      grantSpecial(mole, 1);
      const sim = new Simulation();
      pressSpecial(world, 0, sim);
      expect(mole.action?.kind).toBe('dig');
      for (let t = 0; t < 100; t += 1) {
        if (t === at) {
          place(rabbit, { col: 5, row: 5 });
          sim.step(world, onlyFor(world, 1, press({ bomb: true })));
          expect(world.bombs.map((bomb) => [bomb.cell.col, bomb.cell.row, bomb.owner])).toEqual([[5, 5, 1]]);
          place(rabbit, { col: 19, row: 13 });
          continue;
        }
        sim.step(world, sameForAll(world, press({})));
      }
      expect(pitCells(world)).toEqual(['5,5']);

      place(mole, { col: 1, row: 1 });
      advance(world, sameForAll(world, press({})), 300, sim);
      expect(world.bombs).toEqual([]);
      expect(pitCells(world)).toEqual(['5,5']);
      place(rabbit, { col: 5, row: 5 });
      advance(world, sameForAll(world, press({})), 1, sim);
      expect(rabbit.effects.has('pitfall')).toBe(true);
      expect(pitCells(world)).toEqual([]);
    }
  });

  it('対照：押し出されなければ掘り終わり、足元に穴ができる', () => {
    const world = arena(['mole', 'rabbit']);
    const [mole, rabbit] = world.players as [PlayerState, PlayerState];
    place(mole, { col: 5, row: 5 });
    place(rabbit, { col: 19, row: 13 });
    grantSpecial(mole, 1);
    const sim = new Simulation();
    pressSpecial(world, 0, sim);
    advance(world, onlyFor(world, 0, press({})), 100, sim);
    expect(pitCells(world)).toEqual(['5,5']);
  });
});

describe('落ちる（原型 pitfallCheck）', () => {
  it('もぐらは、ほかのもぐらの穴にも落ちない（穴は残る）', () => {
    const world = arena(['mole', 'mole']);
    const [owner, other] = world.players as [PlayerState, PlayerState];
    place(owner, { col: 3, row: 3 });
    place(other, { col: 7, row: 5 });
    world.actors.push(new PitActor({ col: 7, row: 5 }, owner.id));
    advance(world, sameForAll(world, press({})), 1);
    expect(isFrozen(other)).toBe(false);
    expect(pitCells(world)).toEqual(['7,5']);
  });

  it('対照：もぐらでなければ落ちて動けなくなり、穴は埋まる', () => {
    const world = arena(['mole', 'rabbit']);
    const [owner, rabbit] = world.players as [PlayerState, PlayerState];
    place(owner, { col: 3, row: 3 });
    place(rabbit, { col: 7, row: 5 });
    world.actors.push(new PitActor({ col: 7, row: 5 }, owner.id));
    const sim = new Simulation();
    const events = sim.step(world, sameForAll(world, press({})));
    expect(isFrozen(rabbit)).toBe(true);
    expect(rabbit.effects.has('pitfall')).toBe(true);
    // 泣いている（たまねぎ）のとは別の状態として持つ。
    expect(rabbit.effects.has('stun')).toBe(false);
    expect(events).toContainEqual({ type: 'effectApplied', target: rabbit.id, effect: 'pitfall' });
    expect(pitCells(world)).toEqual([]);
  });

  it('誰も踏まない穴は消えない（4000 tick たっても残り、そのあと踏めば落ちる）', () => {
    // 原型の穴に寿命は無い。消えるのは踏まれたときと、ラウンドが始まり直すときだけ。
    const world = arena(['mole', 'rabbit']);
    const [mole, rabbit] = world.players as [PlayerState, PlayerState];
    place(mole, { col: 1, row: 1 });
    place(rabbit, { col: 19, row: 13 });
    world.actors.push(new PitActor({ col: 7, row: 5 }, mole.id));
    const sim = new Simulation();
    advance(world, sameForAll(world, press({})), 4000, sim);
    expect(pitCells(world)).toEqual(['7,5']);
    place(rabbit, { col: 7, row: 5 });
    sim.step(world, sameForAll(world, press({})));
    expect(rabbit.effects.has('pitfall')).toBe(true);
    expect(pitCells(world)).toEqual([]);
  });

  it('落ちないもぐらが乗り続けても、穴は消えない', () => {
    const world = arena(['mole', 'mole']);
    const [owner, other] = world.players as [PlayerState, PlayerState];
    place(owner, { col: 1, row: 1 });
    place(other, { col: 7, row: 5 });
    world.actors.push(new PitActor({ col: 7, row: 5 }, owner.id));
    advance(world, sameForAll(world, press({})), 4000);
    expect(pitCells(world)).toEqual(['7,5']);
    expect(isFrozen(other)).toBe(false);
  });

  it('2匹のもぐらが同じマスで同時に掘ると、穴は1つで、どちらも落ちない', () => {
    const world = arena(['mole', 'mole']);
    const [m0, m1] = world.players as [PlayerState, PlayerState];
    place(m0, { col: 5, row: 5 });
    place(m1, { col: 5, row: 5 });
    grantSpecial(m0, 1);
    grantSpecial(m1, 1);
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    sim.step(world, sameForAll(world, press({ action: true })));
    expect([m0.action?.kind, m1.action?.kind]).toEqual(['dig', 'dig']);
    advance(world, sameForAll(world, press({})), 100, sim);
    expect(pitCells(world)).toEqual(['5,5']);
    expect([isFrozen(m0), isFrozen(m1)]).toEqual([false, false]);
  });

  it('はまっている間に隣の穴を素通りさせられても落ちず、その穴は残る（原型 181 フレーム）', () => {
    const world = arena(['rabbit', 'mole']);
    const [rabbit, mole] = world.players as [PlayerState, PlayerState];
    place(rabbit, { col: 7, row: 5 });
    place(mole, { col: 1, row: 3 });
    world.actors.push(new PitActor({ col: 7, row: 5 }, mole.id), new PitActor({ col: 8, row: 5 }, mole.id));
    const frozen = countFrozen(world, rabbit, 800, (t) => {
      if (t === 31) place(rabbit, { col: 8, row: 5 });
      if (t === 61) place(rabbit, { col: 9, row: 5 });
    });
    expect(frozen).toBeGreaterThanOrEqual(175);
    expect(frozen).toBeLessThanOrEqual(182);
    expect(pitCells(world)).toEqual(['8,5']);
  });

  it('対照：2つ目の穴の上に居続ければ、切れたときに落ち直す（原型 362 フレーム、穴は残らない）', () => {
    const world = arena(['rabbit', 'mole']);
    const [rabbit, mole] = world.players as [PlayerState, PlayerState];
    place(rabbit, { col: 7, row: 5 });
    place(mole, { col: 1, row: 3 });
    world.actors.push(new PitActor({ col: 7, row: 5 }, mole.id), new PitActor({ col: 8, row: 5 }, mole.id));
    const frozen = countFrozen(world, rabbit, 800, (t) => {
      if (t === 31) place(rabbit, { col: 8, row: 5 });
      // はまっている間は2つ目の穴に落ちず、穴は残る（原型も 100 フレーム目に穴が1つ）。
      // 直す前の形（落とし穴が泣き（'stun'）を上限 360 まで足していた）では、移した直後に落ちても
      // 止まる長さの合計が同じ幅に入り、見分けられなかった。穴が残っていることを直に見る。
      if (t === 100) expect(pitCells(world)).toEqual(['8,5']);
    });
    expect(frozen).toBeGreaterThanOrEqual(355);
    expect(frozen).toBeLessThanOrEqual(365);
    expect(pitCells(world)).toEqual([]);
  });

  it('たまねぎで泣いている相手は穴に落ちる（落とし穴の印だけを見て、泣きは見ない）', () => {
    const world = arena(['rabbit', 'mole']);
    const [rabbit, mole] = world.players as [PlayerState, PlayerState];
    place(rabbit, { col: 7, row: 5 });
    place(mole, { col: 1, row: 3 });
    applyItem(world, rabbit, 'onion');
    world.actors.push(new PitActor({ col: 7, row: 5 }, mole.id));
    advance(world, sameForAll(world, press({})), 1);
    expect(rabbit.effects.has('stun')).toBe(true);
    expect(rabbit.effects.has('pitfall')).toBe(true);
    expect(pitCells(world)).toEqual([]);
  });

  it('落ちたら、バナナの滑りが消える（原型 pitfallCheck の delete p.effects.slide）', () => {
    const world = arena(['rabbit', 'mole']);
    const [rabbit, mole] = world.players as [PlayerState, PlayerState];
    place(rabbit, { col: 6, row: 5 });
    place(mole, { col: 1, row: 3 });
    rabbit.facing = 'right';
    applyItem(world, rabbit, 'banana');
    expect(rabbit.effects.has('slide')).toBe(true);
    world.actors.push(new PitActor({ col: 6, row: 5 }, mole.id));
    advance(world, sameForAll(world, press({})), 1);
    expect(rabbit.effects.has('pitfall')).toBe(true);
    expect(rabbit.effects.has('slide')).toBe(false);
    // 穴が切れたあとも滑り出さない。
    const x = rabbit.position.x;
    advance(world, sameForAll(world, press({})), 200);
    expect(rabbit.position.x).toBe(x);
  });

  it('撒いている最中に落ちても、撒くのは続く（原型 21 マス。撒くのは盤面の側の物が進める）', () => {
    for (const withPit of [false, true]) {
      const world = arena(['rabbit', 'mole']);
      const [rabbit, mole] = world.players as [PlayerState, PlayerState];
      place(rabbit, { col: 5, row: 5 });
      place(mole, { col: 1, row: 3 });
      grantSpecial(rabbit, 1);
      // 押した瞬間の跳躍は、間隔の途中にして出さない（その場で撒かせる）。
      rabbit.abilityCooldown = tick(600);
      const sim = new Simulation();
      sim.step(world, sameForAll(world, press({})));
      for (let i = 0; i < abilityOf('rabbit').holdTicks; i += 1) {
        sim.step(world, onlyFor(world, 0, press({ action: true })));
      }
      expect(rabbit.effects.has('scattering')).toBe(true);
      if (withPit) world.actors.push(new PitActor({ col: 5, row: 5 }, mole.id));
      sim.step(world, sameForAll(world, press({})));
      expect(rabbit.effects.has('pitfall')).toBe(withPit);
      advance(world, sameForAll(world, press({})), 130, sim);
      expect(world.items.filter((item) => item.scatteredBy === rabbit.id)).toHaveLength(21);
    }
  });

  it('突進中に落ちたら、抱えていたハズレを止まった所の左右へ撒く（原型 updateCharge の chargeDrop）', () => {
    for (const [carry, expected] of [
      [['onion'], ['onion@12,3']],
      [['onion', 'poop'], ['onion@12,3', 'poop@12,7']],
    ] as const) {
      const world = arena(['elephant', 'mole']);
      const [elephant, mole] = world.players as [PlayerState, PlayerState];
      place(elephant, { col: 3, row: 5 });
      place(mole, { col: 1, row: 3 });
      carry.forEach((kind, i) => world.items.push({ id: world.ids.take(), cell: { col: 7 + i, row: 5 }, kind }));
      world.actors.push(new PitActor({ col: 12, row: 5 }, mole.id));
      elephant.action = new ChargeAction('right');
      const events: SimEvent[] = [];
      const sim = new Simulation();
      for (let i = 0; i < 120; i += 1) events.push(...sim.step(world, sameForAll(world, press({}))));
      const shown = world.items.map((item) => `${item.kind}@${item.cell.col},${item.cell.row}`);
      expect(shown).toEqual(expected);
      expect(
        events
          .filter((e) => e.type === 'itemDropped')
          .map((e) => (e.type === 'itemDropped' ? `${e.kind}@${e.cell.col},${e.cell.row}` : '')),
      ).toEqual(expected);
      expect(elephant.action).toBeNull();
      // 抱えていたハズレは自分には効かない（泣いていない）。
      expect(elephant.effects.has('stun')).toBe(false);
    }
  });
});

describe('はまっている間の爆弾（原型 canPlaceBomb の !p.effects.pitfall）', () => {
  /** うさぎを穴に落とした世界（落とすのは1 tick 目）。 */
  function fallen(): { world: WorldState; rabbit: PlayerState; sim: Simulation } {
    const world = arena(['rabbit', 'mole']);
    const [rabbit, mole] = world.players as [PlayerState, PlayerState];
    place(rabbit, { col: 7, row: 5 });
    place(mole, { col: 1, row: 3 });
    world.actors.push(new PitActor({ col: 7, row: 5 }, mole.id));
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    expect(rabbit.effects.has('pitfall')).toBe(true);
    return { world, rabbit, sim };
  }

  it('ボタンでは置けない', () => {
    const { world, sim } = fallen();
    sim.step(world, onlyFor(world, 0, press({ bomb: true })));
    expect(world.bombs).toEqual([]);
  });

  it('「勝手に設置」の拍が来ても置かない', () => {
    const { world, rabbit, sim } = fallen();
    rabbit.effects.add('autobomb', itemEffectTicks(4), itemEffectTicks(12));
    sim.step(world, sameForAll(world, press({})));
    expect(world.bombs).toEqual([]);
  });

  it('対照：たまねぎで泣いているだけなら、ボタンで置ける', () => {
    const world = arena(['rabbit', 'mole']);
    const [rabbit, mole] = world.players as [PlayerState, PlayerState];
    place(rabbit, { col: 7, row: 5 });
    place(mole, { col: 1, row: 3 });
    applyItem(world, rabbit, 'onion');
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    sim.step(world, onlyFor(world, 0, press({ bomb: true })));
    expect(world.bombs.map((bomb) => [bomb.cell.col, bomb.cell.row, bomb.owner])).toEqual([[7, 5, 0]]);
  });

  it('対照：たまねぎで泣いているだけなら、「勝手に設置」の拍でも置ける', () => {
    // 原型の答え：(7,5) に置き、泣きはそのまま続く。
    const world = arena(['rabbit', 'mole']);
    const [rabbit, mole] = world.players as [PlayerState, PlayerState];
    place(rabbit, { col: 7, row: 5 });
    place(mole, { col: 1, row: 3 });
    applyItem(world, rabbit, 'onion');
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    rabbit.effects.add('autobomb', itemEffectTicks(4), itemEffectTicks(12));
    sim.step(world, sameForAll(world, press({})));
    expect(world.bombs.map((bomb) => [bomb.cell.col, bomb.cell.row, bomb.owner])).toEqual([[7, 5, 0]]);
    expect(rabbit.effects.has('stun')).toBe(true);
  });
});
