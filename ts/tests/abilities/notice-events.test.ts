import { describe, expect, it } from 'vitest';

import { ChargeAction } from '../../src/domain/abilities/elephant/ChargeAction.js';
import { BurntTongueActor, TONGUE_REACH, TongueAction } from '../../src/domain/abilities/frog/TongueAction.js';
import { centerOf, cellOf, type Cell } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { POOP_EFFECTS, type ItemKind } from '../../src/domain/rules/items.js';
import type { PlayerState } from '../../src/domain/state/PlayerState.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { clearBoard, makeWorld, onlyFor, press, sameForAll } from '../helpers.js';

/**
 * 画面の通知のために足した知らせ（Python 版の `tests/abilities/test_notice_events.py` と同じ場面）。
 *
 * 原型（`legacy/animal-bomber.html`）の通知のうち、それまでのイベントだけでは出せないものがあった
 * （`presentation/notices.ts`）。足したのは2つの種類と3つの項目で、どれも試合の状態を変えない
 * （状態の要約は `tests/determinism/` の検査で見る）。
 *
 * - `techniqueRefused`：根元まで焼けた舌を出そうとした（原型 L2498）
 * - `reachRestored`：焼けた舌が1マス戻った（原型 L4307）
 * - `sprayed.washed`：鼻水で流したうんこの数（原型 L3036）
 * - `effectApplied.pushedBy`：体当たりで抱えていたアイテムを押しつけたプレイヤー（原型 L2880）
 * - `itemTaken.swept`：体当たりで進む間に、通り道のアイテムを吸い込んだか（原型 L2818）
 */

const ACTION = press({ action: true });

/** 壊せるブロックとアイテムを片付けた盤面。0 番は (3, 5) で右を向く。 */
function arena(animals: [string, string]): { world: WorldState; first: PlayerState; second: PlayerState } {
  const world = makeWorld(2468, animals);
  clearBoard(world);
  world.items = [];
  const [first, second] = world.players as [PlayerState, PlayerState];
  first.position = centerOf({ col: 3, row: 5 });
  first.facing = 'right';
  second.position = centerOf({ col: 19, row: 13 });
  return { world, first, second };
}

function putItem(world: WorldState, cell: Cell, kind: ItemKind, extra: { scatteredBy?: 0 | 1; expiresAt?: number; meltingUntil?: number } = {}): void {
  world.items.push({
    id: world.ids.take(),
    cell,
    kind,
    ...(extra.scatteredBy === undefined ? {} : { scatteredBy: extra.scatteredBy }),
    ...(extra.expiresAt === undefined ? {} : { expiresAt: tick(extra.expiresAt) }),
    ...(extra.meltingUntil === undefined ? {} : { meltingUntil: tick(extra.meltingUntil) }),
  });
}

/** 焼けた舌を作り、次に戻るまでの残りを `left` tick にする（作った直後は 600 tick）。 */
function scar(owner: 0 | 1, limit: number, left: number): BurntTongueActor {
  const burnt = new BurntTongueActor(owner, limit);
  for (let i = 0; i < 600 - left; i += 1) burnt.tick();
  expect(burnt.untilRegen).toBe(left);
  return burnt;
}

describe('根元まで焼けた舌を出そうとした', () => {
  it('出せなかったことだけを知らせ、技を出したことにしない（原型の startTongue は、伸ばせる長さが 0 なら通知を出して帰る）', () => {
    const { world, first: frog } = arena(['frog', 'rabbit']);
    world.actors.push(new BurntTongueActor(0, 0));
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    const events = sim.step(world, onlyFor(world, 0, ACTION));
    // 焼けた舌は毎 tick の持ち主の番に1つ戻りへ近づくので、押した tick には 2 減っている。
    expect(events).toEqual([{ type: 'techniqueRefused', player: 0, wait: tick(600 - 2) }]);
    expect(frog.action).toBeNull();
    expect(frog.abilityCooldown).toBe(0);
  });

  it('対照：1マスでも伸ばせれば、ふつうに舌を出す', () => {
    const { world, first: frog } = arena(['frog', 'rabbit']);
    world.actors.push(new BurntTongueActor(0, 1));
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    const events = sim.step(world, onlyFor(world, 0, ACTION));
    expect(events).toContainEqual({ type: 'techniqueUsed', player: 0, special: false });
    expect(events.some((event) => event.type === 'techniqueRefused')).toBe(false);
    expect(frog.action).toBeInstanceOf(TongueAction);
  });

  it('押しっぱなしでは、押した瞬間の1回だけ知らせる', () => {
    const { world } = arena(['frog', 'rabbit']);
    world.actors.push(new BurntTongueActor(0, 0));
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    let refused = 0;
    for (let i = 0; i < 10; i += 1) {
      refused += sim.step(world, onlyFor(world, 0, ACTION)).filter((event) => event.type === 'techniqueRefused').length;
    }
    expect(refused).toBe(1);
  });
});

describe('焼けた舌が戻った', () => {
  it('1マス戻るたびに、戻ったあとの長さを知らせる', () => {
    const { world } = arena(['frog', 'rabbit']);
    world.actors.push(scar(0, 3, 2));
    const sim = new Simulation();
    const idle = sameForAll(world, press({}));
    const restored = (events: readonly SimEvent[]): SimEvent[] => events.filter((event) => event.type === 'reachRestored');
    expect(restored(sim.step(world, idle))).toEqual([]);
    expect(restored(sim.step(world, idle))).toEqual([{ type: 'reachRestored', player: 0, reach: 4 }]);
    const later: SimEvent[] = [];
    for (let i = 0; i < 600 - 1; i += 1) later.push(...restored(sim.step(world, idle)));
    expect(later).toEqual([]);
  });

  it('元の長さまで戻った回にも知らせる（原型 L4305-4307 は「（10マス）」と出す）', () => {
    const { world } = arena(['frog', 'rabbit']);
    world.actors.push(scar(0, TONGUE_REACH - 1, 1));
    const events = new Simulation().step(world, sameForAll(world, press({})));
    expect(events).toContainEqual({ type: 'reachRestored', player: 0, reach: TONGUE_REACH });
    expect(world.actors).toEqual([]);
  });
});

describe('鼻水で流したうんこの数', () => {
  it('流したうんこを数え、撒かれたうんこは数えない', () => {
    const { world } = arena(['elephant', 'rabbit']);
    putItem(world, { col: 4, row: 5 }, 'poop');
    putItem(world, { col: 5, row: 5 }, 'poop', { scatteredBy: 1, expiresAt: 9999 });
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    const events = sim.step(world, onlyFor(world, 0, ACTION));
    expect(events.flatMap((event) => (event.type === 'sprayed' ? [event.washed] : []))).toEqual([1]);
  });

  it('溶けかけのうんこに吹き直しても数え（原型は溶けかけのものにも数を足す L3021-3023）、何も無ければ 0', () => {
    const { world, first: elephant } = arena(['elephant', 'rabbit']);
    putItem(world, { col: 4, row: 5 }, 'poop', { meltingUntil: world.now + 5 });
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    const washed = (events: readonly SimEvent[]): number[] =>
      events.flatMap((event) => (event.type === 'sprayed' ? [event.washed] : []));
    expect(washed(sim.step(world, onlyFor(world, 0, ACTION)))).toEqual([1]);
    world.items = [];
    elephant.abilityCooldown = tick(0);
    sim.step(world, sameForAll(world, press({})));
    expect(washed(sim.step(world, onlyFor(world, 0, ACTION)))).toEqual([0]);
  });
});

describe('押しつけたプレイヤー', () => {
  it('体当たりで押しつけた状態には、押しつけたプレイヤーを載せる', () => {
    const { world, first: elephant, second: victim } = arena(['elephant', 'rabbit']);
    for (const player of world.players) player.invulnerableUntil = tick(9999);
    victim.position = centerOf({ col: 8, row: 5 });
    putItem(world, { col: 4, row: 5 }, 'onion');
    putItem(world, { col: 5, row: 5 }, 'banana');
    elephant.action = new ChargeAction('right');
    const sim = new Simulation();
    const pushed: SimEvent[] = [];
    for (let i = 0; i < 120 && pushed.length === 0; i += 1) {
      pushed.push(...sim.step(world, sameForAll(world, press({}))).filter((event) => event.type === 'effectApplied'));
    }
    expect(pushed).toEqual([
      { type: 'effectApplied', target: 1, effect: 'stun', pushedBy: 0 },
      { type: 'effectApplied', target: 1, effect: 'slide', pushedBy: 0 },
    ]);
  });

  it('うんこを押しつけても、かかった状態に押しつけたプレイヤーを載せる（かかる状態の種類は試合の乱数で決まる）', () => {
    const { world, first: elephant, second: victim } = arena(['elephant', 'rabbit']);
    for (const player of world.players) player.invulnerableUntil = tick(9999);
    victim.position = centerOf({ col: 8, row: 5 });
    putItem(world, { col: 4, row: 5 }, 'poop');
    elephant.action = new ChargeAction('right');
    const sim = new Simulation();
    const pushed: SimEvent[] = [];
    for (let i = 0; i < 120 && pushed.length === 0; i += 1) {
      pushed.push(...sim.step(world, sameForAll(world, press({}))).filter((event) => event.type === 'effectApplied'));
    }
    expect(pushed).toEqual([
      { type: 'effectApplied', target: 1, effect: expect.toBeOneOf(POOP_EFFECTS.map((poop) => poop.kind)), pushedBy: 0 },
    ]);
  });

  it('自分で拾った状態には載せない', () => {
    const { world, second: rabbit } = arena(['elephant', 'rabbit']);
    putItem(world, cellOf(rabbit.position), 'banana');
    const events = new Simulation().step(world, sameForAll(world, press({})));
    expect(events).toContainEqual({ type: 'effectApplied', target: 1, effect: 'slide', pushedBy: null });
  });
});

describe('体当たりで吸い込んだ', () => {
  it('体当たりで進む間に取った良いアイテムには吸い込んだ印を付け、足元で拾ったものには付けない', () => {
    const { world, first: elephant, second: rabbit } = arena(['elephant', 'rabbit']);
    putItem(world, { col: 4, row: 5 }, 'fire');
    putItem(world, cellOf(rabbit.position), 'shoe');
    elephant.action = new ChargeAction('right');
    const sim = new Simulation();
    const taken: SimEvent[] = [];
    for (let i = 0; i < 30; i += 1) {
      taken.push(...sim.step(world, sameForAll(world, press({}))).filter((event) => event.type === 'itemTaken'));
    }
    expect(taken).toEqual([
      { type: 'itemTaken', cell: cellOf(rabbit.position), kind: 'shoe', taker: 1, swept: false },
      { type: 'itemTaken', cell: { col: 4, row: 5 }, kind: 'fire', taker: 0, swept: true },
    ]);
  });

  it('舌で引き寄せたアイテムには、吸い込んだ印を付けない（付けると「… を吸い込んだ！」が出る）', () => {
    const { world } = arena(['frog', 'rabbit']);
    putItem(world, { col: 6, row: 5 }, 'fire');
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    const taken = (events: readonly SimEvent[]): SimEvent[] => events.filter((event) => event.type === 'itemTaken');
    const all = taken(sim.step(world, onlyFor(world, 0, ACTION)));
    for (let i = 0; i < 60; i += 1) all.push(...taken(sim.step(world, sameForAll(world, press({})))));
    expect(all).toEqual([{ type: 'itemTaken', cell: null, kind: 'fire', taker: 0, swept: false }]);
  });
});
