import { describe, expect, it } from 'vitest';

import type { WorldActor } from '../../src/domain/abilities/WorldActor.js';
import { FoxfireActor } from '../../src/domain/abilities/fox/FoxfireActor.js';
import { SlimeBombActor } from '../../src/domain/abilities/frog/SlimeBombActor.js';
import { BurntTongueActor } from '../../src/domain/abilities/frog/TongueAction.js';
import { PitActor } from '../../src/domain/abilities/mole/PitAction.js';
import { ScatterActor } from '../../src/domain/abilities/rabbit/ScatterActor.js';
import { centerOf } from '../../src/domain/core/Coord.js';
import { LeekActor } from '../../src/domain/negibon/LeekActor.js';
import { hashWorld, type WorldState } from '../../src/domain/state/WorldState.js';
import { clearBoard, makeWorld } from '../helpers.js';

/*
 * 盤面の物の要約（`encode`）は、状態の要約（`hashWorld`）に混ぜて、通信対戦のずれを見つけるのに使う。
 * 状態が進んでも要約が変わらない盤面の物があると、その物の進み方が端末ごとにずれても見つからない。
 * どの盤面の物も、1 tick 進むたびに要約が変わることを確認する（Python 版は `tests/state/test_world.py` の
 * 項目ごとの表）。
 */

function arena(): WorldState {
  const world = makeWorld(5, ['frog', 'fox']);
  clearBoard(world);
  world.items = [];
  world.players[0]!.position = centerOf({ col: 3, row: 7 });
  world.players[1]!.position = centerOf({ col: 15, row: 7 });
  return world;
}

const MOVING: readonly [string, (world: WorldState) => WorldActor][] = [
  ['追いかける炎', (world) => new FoxfireActor(world.players[1]!.position, 1)],
  ['撒く本体', () => new ScatterActor({ col: 9, row: 9 }, 0)],
  ['跳ねる爆弾', (world) => SlimeBombActor.launch(world, world.players[0]!)],
  ['焼けた舌', () => new BurntTongueActor(0, 2)],
  ['葱', () => new LeekActor({ x: 5.5, y: -0.6 }, 'down', 1)],
];

describe('盤面の物の要約（encode）', () => {
  it.each(MOVING)('%s：1 tick 進むたびに要約が変わり、状態の要約も変わる', (_name, make) => {
    const world = arena();
    const actor = make(world);
    world.actors.push(actor);
    let advanced = 0;
    for (let t = 0; t < 30; t += 1) {
      const before = actor.encode();
      const hash = hashWorld(world);
      const { done } = actor.tick(world);
      if (done) break;
      expect(actor.encode(), `${t + 1} tick 目`).not.toBe(before);
      expect(hashWorld(world), `${t + 1} tick 目`).not.toBe(hash);
      advanced += 1;
    }
    // 1 tick で終わってしまうと、確認にならない。
    expect(advanced).toBeGreaterThanOrEqual(5);
  });

  it('落とし穴は進まない（要約は変わらない）。マスか持ち主が違えば要約が違う', () => {
    const world = arena();
    const pit = new PitActor({ col: 9, row: 9 }, 0);
    world.actors.push(pit);
    const before = pit.encode();
    expect(pit.tick(world).done).toBe(false);
    expect(pit.encode()).toBe(before);
    expect(new PitActor({ col: 9, row: 10 }, 0).encode()).not.toBe(before);
    expect(new PitActor({ col: 9, row: 9 }, 1).encode()).not.toBe(before);
  });
});
