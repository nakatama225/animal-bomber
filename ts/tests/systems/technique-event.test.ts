import { describe, expect, it } from 'vitest';

import { abilityOf } from '../../src/domain/abilities/registry.js';
import { centerOf } from '../../src/domain/core/Coord.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { clearBoard, makeWorld, onlyFor, press } from '../helpers.js';

/**
 * 技を使ったことを知らせるイベント。
 *
 * 音を当てるのは描画と音の層で、ルールの層は「誰が、通常技かとくぎかを
 * 使ったか」だけを知らせる。何の技かは言わない（動物を知らないまま出せる）。
 */

function techniqueEvents(events: readonly SimEvent[]) {
  return events.filter((e) => e.type === 'techniqueUsed');
}

function tapEvents(world: ReturnType<typeof makeWorld>, sim: Simulation): SimEvent[] {
  const events: SimEvent[] = [];
  events.push(...sim.step(world, onlyFor(world, 0, press({}))));
  events.push(...sim.step(world, onlyFor(world, 0, press({ action: true }))));
  events.push(...sim.step(world, onlyFor(world, 0, press({}))));
  return events;
}

describe('技を使ったイベント', () => {
  it('通常技が出たら、とくぎではない技として知らせる', () => {
    const world = makeWorld(3, ['rabbit', 'elephant']);
    clearBoard(world);
    world.players[0]!.position = centerOf({ col: 1, row: 1 });
    world.players[0]!.facing = 'right';
    const events = techniqueEvents(tapEvents(world, new Simulation()));
    expect(events).toEqual([{ type: 'techniqueUsed', player: 0, special: false }]);
  });

  it('間隔中に押して何も起きなかったときは知らせない', () => {
    // 押しただけで音が鳴ると、技が出たと勘違いさせる。
    const world = makeWorld(3, ['rabbit', 'elephant']);
    clearBoard(world);
    world.players[0]!.facing = 'right';
    const sim = new Simulation();
    tapEvents(world, sim);
    expect(techniqueEvents(tapEvents(world, sim))).toEqual([]);
  });

  it('とくぎが出たら、とくぎとして知らせる', () => {
    const world = makeWorld(3, ['elephant', 'rabbit']);
    world.players[0]!.specialCharges = 1;
    const sim = new Simulation();
    const events: SimEvent[] = [...sim.step(world, onlyFor(world, 0, press({})))];
    for (let i = 0; i < abilityOf('elephant').holdTicks; i += 1) {
      events.push(...sim.step(world, onlyFor(world, 0, press({ action: true }))));
    }
    expect(techniqueEvents(events)).toEqual([{ type: 'techniqueUsed', player: 0, special: true }]);
  });
});
