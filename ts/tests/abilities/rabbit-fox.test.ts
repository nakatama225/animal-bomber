import { describe, expect, it } from 'vitest';

import { SlimeBombActor } from '../../src/domain/abilities/frog/SlimeBombActor.js';
import { TongueAction } from '../../src/domain/abilities/frog/TongueAction.js';
import { PitActor } from '../../src/domain/abilities/mole/PitAction.js';
import { ScatterActor } from '../../src/domain/abilities/rabbit/ScatterActor.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
import { cellOf, centerOf, type Cell } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import { placeBombAt } from '../../src/domain/mutations/bombs.js';
import { itemEffectTicks } from '../../src/domain/rules/items.js';
import type { PlayerState } from '../../src/domain/state/PlayerState.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { advance, clearBoard, grantSpecial, makeWorld, onlyFor, press, sameForAll } from '../helpers.js';

/*
 * うさぎの撒くのと、きつねの一列置きを、原型（legacy/animal-bomber.html の rabbitPoroporo・
 * updatePoroporos・pickupCheck・updateTongue・canPlaceBomb・foxLineShot）に合わせる。
 * 期待値は原型を画面なしで動かして測った値。原型はとくぎを出した直後のフレームを 1 と数えた。
 */

/** 悪いアイテムのうんこの抽選でかかりうる状態。 */
const POOP_EFFECTS = ['reverse', 'nobomb', 'runaway', 'weak', 'autobomb', 'slow'] as const;

function arena(animals: [string, string]): { world: WorldState; p0: PlayerState; p1: PlayerState } {
  const world = makeWorld(1234, animals);
  clearBoard(world);
  world.items = [];
  const [p0, p1] = world.players as [PlayerState, PlayerState];
  p1.position = centerOf({ col: 19, row: 13 });
  return { world, p0, p1 };
}

function place(player: PlayerState, cell: Cell): void {
  player.position = centerOf(cell);
}

/**
 * 0番に技のボタンを長押しさせて、とくぎを出す（ラウンドの始まりの「出し終えた扱い」を外すため、まず離す）。
 *
 * 押した瞬間の通常技（跳躍）は、間隔の途中にして出さない。その場で撒かせる。
 */
function holdSpecial(world: WorldState, sim: Simulation): void {
  const player = world.players[0]!;
  grantSpecial(player, 1);
  player.abilityCooldown = tick(600);
  sim.step(world, sameForAll(world, press({})));
  for (let i = 0; i < abilityOf(player.animal).holdTicks; i += 1) {
    sim.step(world, onlyFor(world, 0, press({ action: true })));
  }
}

const scatteredCells = (world: WorldState): string[] =>
  world.items
    .filter((item) => item.scatteredBy !== undefined)
    .map((item) => `${item.cell.col},${item.cell.row}`);

/** 撒いたうんこを1つ置く。 */
function scatteredPoop(world: WorldState, cell: Cell, owner: PlayerState): void {
  world.items.push({
    id: world.ids.take(),
    cell,
    kind: 'poop',
    scatteredBy: owner.id,
    expiresAt: tick(world.now + 3600),
  });
}

describe('撒く順と時刻（原型 updatePoroporos）', () => {
  it('足元・1周目・2周目の輪を 1・40・80 tick 目に撒き、輪の中は上の行から、行の中は左から', () => {
    const { world, p0: rabbit } = arena(['rabbit', 'frog']);
    place(rabbit, { col: 9, row: 7 });
    const scatter = new ScatterActor({ col: 9, row: 7 }, rabbit.id);
    const counts: number[] = [];
    const order: string[] = [];
    let done = false;
    for (let t = 1; t <= 130; t += 1) {
      if (!done) done = scatter.tick(world).done;
      for (const cell of scatteredCells(world)) if (!order.includes(cell)) order.push(cell);
      counts.push(scatteredCells(world).length);
    }
    const at = counts.flatMap((n, i) => (i === 0 || n !== counts[i - 1] ? [`${i + 1}:${n}`] : []));
    expect(at).toEqual(['1:1', '40:5', '80:21']);
    expect(order).toEqual([
      '9,7',
      '9,6', '8,7', '10,7', '9,8',
      '7,5', '8,5', '9,5', '10,5', '11,5', '7,6', '11,6', '7,7', '11,7', '7,8', '11,8', '7,9', '8,9', '9,9', '10,9', '11,9',
    ]);
    expect(done).toBe(true);
  });

  it('撒いている間も跳べる（撒くのは盤面の側の物が続け、うさぎは乗っ取られない）', () => {
    const { world, p0: rabbit } = arena(['rabbit', 'frog']);
    place(rabbit, { col: 3, row: 7 });
    rabbit.facing = 'right';
    const sim = new Simulation();
    holdSpecial(world, sim);
    expect(rabbit.action).toBeNull();
    expect(rabbit.effects.has('scattering')).toBe(true);
    expect(rabbit.position.x).toBe(3.5);
    advance(world, sameForAll(world, press({})), 10, sim);
    rabbit.abilityCooldown = tick(0);
    sim.step(world, onlyFor(world, 0, press({ action: true })));
    sim.step(world, sameForAll(world, press({})));
    expect(rabbit.position.x).toBe(5.5);
    expect(world.actors.some((actor) => actor instanceof ScatterActor)).toBe(true);
  });
});

describe('撒いたうんこ（原型の poro のアイテム）', () => {
  it('撒いたプレイヤー自身は踏んでも効かず残る。ほかのプレイヤーは踏むと消えて、うんこの抽選がかかる', () => {
    const { world, p0: rabbit, p1: frog } = arena(['rabbit', 'frog']);
    place(rabbit, { col: 3, row: 7 });
    scatteredPoop(world, { col: 3, row: 7 }, rabbit);
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    expect(POOP_EFFECTS.filter((kind) => rabbit.effects.has(kind))).toEqual([]);
    expect(scatteredCells(world)).toEqual(['3,7']);

    scatteredPoop(world, cellOf(frog.position), rabbit);
    sim.step(world, sameForAll(world, press({})));
    expect(POOP_EFFECTS.filter((kind) => frog.effects.has(kind))).toHaveLength(1);
    expect(scatteredCells(world)).toEqual(['3,7']);
  });

  it('爆風では消えない（対照：ふつうのアイテムは焼ける）', () => {
    const { world, p0: rabbit, p1: frog } = arena(['rabbit', 'frog']);
    place(rabbit, { col: 1, row: 1 });
    scatteredPoop(world, { col: 7, row: 7 }, rabbit);
    world.items.push({ id: world.ids.take(), cell: { col: 9, row: 7 }, kind: 'fire' });
    placeBombAt(world, frog, { col: 8, row: 7 })!.fuse = tick(1);
    advance(world, sameForAll(world, press({})), 2);
    expect(world.items.map((item) => `${item.kind}@${item.cell.col},${item.cell.row}`)).toEqual(['poop@7,7']);
  });

  it('置かれた tick から 3601 tick 目に消える（原型は 60 秒より長く経ったら消す）', () => {
    const { world, p0: rabbit } = arena(['rabbit', 'frog']);
    place(rabbit, { col: 1, row: 1 });
    world.actors.push(new ScatterActor({ col: 7, row: 7 }, rabbit.id));
    const sim = new Simulation();
    const atCenter = (): boolean => world.items.some((item) => item.cell.col === 7 && item.cell.row === 7);
    let placedAt: number | null = null;
    let goneAt: number | null = null;
    for (let t = 1; t <= 3800 && goneAt === null; t += 1) {
      const events = sim.step(world, sameForAll(world, press({})));
      if (placedAt === null && atCenter()) placedAt = t;
      if (placedAt !== null && !atCenter()) {
        goneAt = t;
        expect(events).toContainEqual({ type: 'itemExpired', cell: { col: 7, row: 7 }, kind: 'poop', scattered: true });
      }
    }
    expect(placedAt).toBe(1);
    expect(goneAt).toBe(3602);
  });

  it('かえるの舌で掴め、かえるに効く（2倍）', () => {
    const { world, p0: frog, p1: rabbit } = arena(['frog', 'rabbit']);
    place(frog, { col: 3, row: 7 });
    frog.facing = 'right';
    scatteredPoop(world, { col: 6, row: 7 }, rabbit);
    const tongue = new TongueAction(cellOf(frog.position), frog.facing);
    for (let t = 0; t < 60; t += 1) if (tongue.tick(world, frog).done) break;
    expect(world.items).toEqual([]);
    expect(POOP_EFFECTS.filter((kind) => frog.effects.has(kind))).toHaveLength(1);
  });
});

describe('撒く範囲（原型 updatePoroporos）', () => {
  it('落とし穴のマスにも撒く（穴の位置がばれない。穴は残る）', () => {
    const { world, p0: rabbit, p1: mole } = arena(['rabbit', 'mole']);
    place(rabbit, { col: 5, row: 5 });
    world.actors.push(new PitActor({ col: 6, row: 5 }, mole.id));
    const sim = new Simulation();
    holdSpecial(world, sim);
    advance(world, sameForAll(world, press({})), 130, sim);
    const cells = scatteredCells(world);
    expect(cells).toContain('6,5');
    expect(cells).toHaveLength(21);
    expect(world.actors.some((actor) => actor instanceof PitActor)).toBe(true);
  });

  it('粘膜爆弾が乗っているマスにも撒く', () => {
    const { world, p0: rabbit } = arena(['rabbit', 'frog']);
    place(rabbit, { col: 5, row: 5 });
    world.actors.push(new SlimeBombActor({ col: 6, row: 5 }, rabbit, 8));
    // 粘膜爆弾を跳ばさないため、撒く本体だけを直に進める。
    const scatter = new ScatterActor({ col: 5, row: 5 }, rabbit.id);
    for (let i = 0; i < 120; i += 1) scatter.tick(world);
    const cells = scatteredCells(world);
    expect(cells).toContain('6,5');
    expect(cells).toHaveLength(21);
  });

  it('対照：続けて撒いても、撒き済みのマスには重ねない（原型 21 → 24）', () => {
    const { world, p0: rabbit } = arena(['rabbit', 'frog']);
    place(rabbit, { col: 5, row: 5 });
    const first = new ScatterActor({ col: 5, row: 5 }, rabbit.id);
    for (let i = 0; i < 120; i += 1) first.tick(world);
    expect(scatteredCells(world)).toHaveLength(21);
    const second = new ScatterActor({ col: 6, row: 5 }, rabbit.id);
    for (let i = 0; i < 120; i += 1) second.tick(world);
    const cells = scatteredCells(world);
    expect(cells).toHaveLength(24);
    expect(new Set(cells).size).toBe(24);
  });

  it('2つが同じ tick に同じマスへ撒くと、新しいほうのうんこになる（原型 updatePoroporos は配列を後ろから回す L2756）', () => {
    // 原型：中心 (5,7) の A（古い）と (7,7) の B（新しい）を同じ update から撒くと、B が先に撒き、A はアイテムのある
    // マスを飛ばす（L2768）。40 フレーム目の 1周目どうしの (6,7) と、80 フレーム目の 2周目どうしの (5,5)・(6,5)・(7,5)・
    // (5,9)・(6,9)・(7,9) は B のもの。持ち主ごとのマスは、原型を画面なしで動かして見た並び。
    const { world, p0, p1 } = arena(['rabbit', 'rabbit']);
    place(p0, { col: 1, row: 1 });
    world.actors.push(new ScatterActor({ col: 5, row: 7 }, p0.id), new ScatterActor({ col: 7, row: 7 }, p1.id));
    advance(world, sameForAll(world, press({})), 130);
    const ownedBy = (owner: PlayerState): string[] =>
      world.items.filter((item) => item.scatteredBy === owner.id).map((item) => `${item.cell.col},${item.cell.row}`);
    expect(ownedBy(p0)).toEqual(['5,7', '5,6', '4,7', '5,8', '3,5', '4,5', '3,6', '3,7', '3,8', '3,9', '4,9']);
    expect(ownedBy(p1)).toEqual([
      '7,7', '7,6', '6,7', '8,7', '7,8',
      '5,5', '6,5', '7,5', '8,5', '9,5', '9,6', '9,7', '9,8', '5,9', '6,9', '7,9', '8,9', '9,9',
    ]);
  });
});

describe('撒いている間の爆弾（原型 canPlaceBomb は撒いている状態を見ない）', () => {
  it('ボタンで置ける', () => {
    const { world, p0: rabbit } = arena(['rabbit', 'mole']);
    place(rabbit, { col: 3, row: 1 });
    const sim = new Simulation();
    holdSpecial(world, sim);
    expect(rabbit.effects.has('scattering')).toBe(true);
    sim.step(world, onlyFor(world, 0, press({ bomb: true })));
    expect(world.bombs.map((bomb) => [bomb.cell.col, bomb.cell.row, bomb.owner])).toEqual([[3, 1, 0]]);
  });

  it('「勝手に設置」の拍で置く', () => {
    const { world, p0: rabbit } = arena(['rabbit', 'mole']);
    place(rabbit, { col: 3, row: 1 });
    const sim = new Simulation();
    holdSpecial(world, sim);
    expect(rabbit.effects.has('scattering')).toBe(true);
    rabbit.effects.add('autobomb', itemEffectTicks(4), itemEffectTicks(12));
    sim.step(world, sameForAll(world, press({})));
    expect(world.bombs.map((bomb) => [bomb.cell.col, bomb.cell.row, bomb.owner])).toEqual([[3, 1, 0]]);
  });
});

describe('一列置きと「爆弾おけない」（原型 foxLineShot の canPlaceBomb）', () => {
  /** きつねを (1,1) 右向きに置き、手持ち3。効果をかけてから押して離す。 */
  function line(effects: ('nobomb' | 'autobomb')[]) {
    const { world, p0: fox } = arena(['fox', 'rabbit']);
    place(fox, { col: 1, row: 1 });
    fox.facing = 'right';
    fox.maxBombs = 3;
    for (const effect of effects) fox.effects.add(effect, itemEffectTicks(4), itemEffectTicks(12));
    // 勝手に設置の拍は来ないようにする（技の確かめだけを見る）。
    fox.autobombWait = tick(99);
    const sim = new Simulation();
    sim.step(world, sameForAll(world, press({})));
    sim.step(world, onlyFor(world, 0, press({ action: true })));
    sim.step(world, sameForAll(world, press({})));
    return {
      bombs: world.bombs.map((bomb) => `${bomb.cell.col},${bomb.cell.row}`),
      cooldown: fox.abilityCooldown,
    };
  }

  it('「爆弾おけない」の間は、一列置きもできない（間隔も始まらない）', () => {
    expect(line(['nobomb'])).toEqual({ bombs: [], cooldown: 0 });
  });

  it('「勝手に設置」も重なっていれば置ける（勝手に設置が勝つ）', () => {
    expect(line(['nobomb', 'autobomb']).bombs).toEqual(['2,1', '3,1', '4,1']);
  });

  it('対照：何もかかっていなければ、1マス前から手持ちのぶん並べる', () => {
    expect(line([]).bombs).toEqual(['2,1', '3,1', '4,1']);
  });
});
