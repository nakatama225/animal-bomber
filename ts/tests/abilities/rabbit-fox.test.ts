import { describe, expect, it } from 'vitest';

import { SlimeBombActor } from '../../src/domain/abilities/frog/SlimeBombActor.js';
import { PitActor } from '../../src/domain/abilities/mole/PitAction.js';
import { ScatterAction, ScatteredActor } from '../../src/domain/abilities/rabbit/ScatterAction.js';
import { abilityOf } from '../../src/domain/abilities/registry.js';
import { centerOf, type Cell } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import { itemEffectTicks } from '../../src/domain/rules/items.js';
import type { PlayerState } from '../../src/domain/state/PlayerState.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { advance, clearBoard, makeWorld, onlyFor, press, sameForAll } from '../helpers.js';

/*
 * うさぎの撒くのと、きつねの一列置きを、原型（legacy/animal-bomber.html の rabbitPoroporo・
 * updatePoroporos・canPlaceBomb・foxLineShot）に合わせる。期待値は原型を画面なしで動かして測った値。
 */

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

/** 0番に技のボタンを長押しさせて、とくぎを出す（ラウンドの始まりのロックを外すため、まず離す）。 */
function holdSpecial(world: WorldState, sim: Simulation): void {
  const player = world.players[0]!;
  player.specialCharges = 1;
  sim.step(world, sameForAll(world, press({})));
  for (let i = 0; i < abilityOf(player.animal).holdTicks; i += 1) {
    sim.step(world, onlyFor(world, 0, press({ action: true })));
  }
}

const scatteredCells = (world: WorldState): string[] =>
  world.actors
    .filter((actor): actor is ScatteredActor => actor instanceof ScatteredActor)
    .map((actor) => `${actor.cell.col},${actor.cell.row}`);

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
    // 粘膜爆弾を跳ばさないため、撒く振る舞いだけを直に進める。
    const scatter = new ScatterAction({ col: 5, row: 5 });
    for (let i = 0; i < 120; i += 1) scatter.tick(world, rabbit);
    const cells = scatteredCells(world);
    expect(cells).toContain('6,5');
    expect(cells).toHaveLength(21);
  });

  it('対照：続けて撒いても、撒き済みのマスには重ねない（原型 21 → 24）', () => {
    const { world, p0: rabbit } = arena(['rabbit', 'frog']);
    place(rabbit, { col: 5, row: 5 });
    const first = new ScatterAction({ col: 5, row: 5 });
    for (let i = 0; i < 120; i += 1) first.tick(world, rabbit);
    expect(scatteredCells(world)).toHaveLength(21);
    const second = new ScatterAction({ col: 6, row: 5 });
    for (let i = 0; i < 120; i += 1) second.tick(world, rabbit);
    const cells = scatteredCells(world);
    expect(cells).toHaveLength(24);
    expect(new Set(cells).size).toBe(24);
  });
});

describe('撒いている間の爆弾（原型 canPlaceBomb は撒いている状態を見ない）', () => {
  it('ボタンで置ける', () => {
    const { world, p0: rabbit } = arena(['rabbit', 'mole']);
    place(rabbit, { col: 3, row: 1 });
    const sim = new Simulation();
    holdSpecial(world, sim);
    expect(rabbit.action?.kind).toBe('scatter');
    sim.step(world, onlyFor(world, 0, press({ bomb: true })));
    expect(world.bombs.map((bomb) => [bomb.cell.col, bomb.cell.row, bomb.owner])).toEqual([[3, 1, 0]]);
  });

  it('「勝手に設置」の拍で置く', () => {
    const { world, p0: rabbit } = arena(['rabbit', 'mole']);
    place(rabbit, { col: 3, row: 1 });
    const sim = new Simulation();
    holdSpecial(world, sim);
    expect(rabbit.action?.kind).toBe('scatter');
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
