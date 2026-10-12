import { describe, expect, it } from 'vitest';

import { ScatterActor } from '../../src/domain/abilities/rabbit/ScatterActor.js';
import { centerOf, type Cell } from '../../src/domain/core/Coord.js';
import { tick } from '../../src/domain/core/Tick.js';
import type { SimEvent } from '../../src/domain/events/SimEvent.js';
import { placeBombAt } from '../../src/domain/mutations/bombs.js';
import type { PlayerState } from '../../src/domain/state/PlayerState.js';
import type { WorldState } from '../../src/domain/state/WorldState.js';
import { Simulation } from '../../src/domain/systems/Simulation.js';
import { clearBoard, makeWorld, onlyFor, press } from '../helpers.js';

/*
 * とくぎを直に出すボタン（`PlayerInput.special`）。人間の操作には割り当てず、CPU だけが押す。
 *
 * 原型の CPU は、ボタンを通らずに useSpecial を直に呼んでいた。長押しの待ちが無く、押した瞬間の
 * 通常技（跳ぶ・鼻水・一列・舌）も出ない。この版の CPU は入力しか返せないので、このボタンで同じ出し方をする。
 * 出せる条件は長押しのとくぎ（原型の doSpecial）と同じ：泣いている・はまっている・舌の最中は出ず、
 * チキンが無ければ何もしない。
 */

interface Scene {
  readonly world: WorldState;
  readonly me: PlayerState;
  readonly foe: PlayerState;
  readonly sim: Simulation;
}

function place(player: PlayerState, cell: Cell): void {
  player.position = centerOf(cell);
}

/** 0番を (3,7) 右向き、1番を (19,13) に置き、0番にチキン1つ。 */
function duel(animal: string, other = 'frog'): Scene {
  const world = makeWorld(2468, [animal, other]);
  clearBoard(world);
  world.items = [];
  const [me, foe] = world.players as [PlayerState, PlayerState];
  place(me, { col: 3, row: 7 });
  me.facing = 'right';
  place(foe, { col: 19, row: 13 });
  me.specialCharges = 1;
  me.actionFired = false;
  return { world, me, foe, sim: new Simulation() };
}

/** 0番だけが `special` を押す・離す、を tick ごとに決めて流す。 */
function run(scene: Scene, ticks: number, pressed: (t: number) => boolean): SimEvent[] {
  const events: SimEvent[] = [];
  for (let t = 1; t <= ticks; t += 1) {
    events.push(...scene.sim.step(scene.world, onlyFor(scene.world, 0, press({ special: pressed(t) }))));
  }
  return events;
}

/** 0番の技の知らせ（とくぎなら true、通常技なら false）。 */
function techniques(events: readonly SimEvent[]): boolean[] {
  return events.flatMap((event) => (event.type === 'techniqueUsed' && event.player === 0 ? [event.special] : []));
}

describe('とくぎを直に出すボタン（原型の CPU の useSpecial）', () => {
  it('うさぎ：押した tick に、跳ばずにその場で撒く', () => {
    const scene = duel('rabbit');
    const events = run(scene, 1, () => true);
    expect(scene.me.position.x).toBe(3.5);
    expect(scene.world.actors.some((actor) => actor instanceof ScatterActor)).toBe(true);
    expect(scene.me.specialCharges).toBe(0);
    expect(techniques(events)).toEqual([true]);
  });

  it('ぞう：押した tick に突進が始まり、鼻水は出ない（2マス先の爆弾は消えない）', () => {
    const scene = duel('elephant');
    placeBombAt(scene.world, scene.foe, { col: 5, row: 7 })!.fuse = tick(999);
    const events = run(scene, 1, () => true);
    expect(scene.me.action?.kind).toBe('charge');
    expect(scene.world.bombs).toHaveLength(1);
    expect(scene.me.abilityCooldown).toBe(0);
    expect(techniques(events)).toEqual([true]);
  });

  it('きつね：押した tick に跳び、一列は置かない', () => {
    const scene = duel('fox');
    const events = run(scene, 1, () => true);
    expect(scene.me.effects.has('leap')).toBe(true);
    expect(scene.world.bombs).toEqual([]);
    expect(techniques(events)).toEqual([true]);
  });

  it('押しっぱなしでも1回だけ出る。離して押し直すと、もう1回出る', () => {
    const scene = duel('fox');
    scene.me.specialCharges = 2;
    const held = run(scene, 60, () => true);
    expect(techniques(held)).toEqual([true]);
    expect(scene.me.specialCharges).toBe(1);
    const again = run(scene, 2, (t) => t === 2);
    expect(techniques(again)).toEqual([true]);
    expect(scene.me.specialCharges).toBe(0);
  });

  it('チキンが無ければ何も出ない（通常技も出ない）', () => {
    const scene = duel('rabbit');
    scene.me.specialCharges = 0;
    const events = run(scene, 1, () => true);
    expect(scene.me.position.x).toBe(3.5);
    expect(scene.world.actors).toEqual([]);
    expect(techniques(events)).toEqual([]);
  });

  it('泣いている・はまっている間は出ず、チキンも減らない', () => {
    for (const effect of ['stun', 'pitfall'] as const) {
      const scene = duel('rabbit');
      scene.me.effects.add(effect, tick(240), tick(240));
      const events = run(scene, 1, () => true);
      expect(techniques(events)).toEqual([]);
      expect(scene.me.specialCharges).toBe(1);
      expect(scene.world.actors).toEqual([]);
    }
  });

  it('舌の最中は出ず、チキンも減らない', () => {
    const scene = duel('frog', 'fox');
    scene.sim.step(scene.world, onlyFor(scene.world, 0, press({ action: true })));
    expect(scene.me.action?.kind).toBe('tongue');
    const events = run(scene, 1, () => true);
    expect(techniques(events)).toEqual([]);
    expect(scene.me.specialCharges).toBe(1);
    expect(scene.world.actors.some((actor) => actor.kind === 'slime')).toBe(false);
  });

  it('技のボタンの押した長さと、とくぎを出し終えた印には触れない', () => {
    // 長押しの数え方は技のボタンだけのもの。このボタンを押しても、数え直しも出し終えた扱いも起きない。
    const scene = duel('fox');
    scene.me.specialCharges = 2;
    for (let t = 1; t <= 10; t += 1) {
      scene.sim.step(scene.world, onlyFor(scene.world, 0, press({ action: true })));
    }
    scene.sim.step(scene.world, onlyFor(scene.world, 0, press({ action: true, special: true })));
    expect([scene.me.actionHeld, scene.me.actionFired]).toEqual([11, false]);
  });
});
