import type { WorldActor } from '../../domain/abilities/WorldActor.js';
import { FoxfireActor } from '../../domain/abilities/fox/FoxfireActor.js';
import { PitActor } from '../../domain/abilities/mole/PitAction.js';
import { cellOf } from '../../domain/core/Coord.js';
import type { WorldState } from '../../domain/state/WorldState.js';
import type { CosmeticRng } from '../CosmeticRng.js';
import { glow, puff, type Particle } from './particles.js';

/**
 * 追いかける炎の通った跡を、何 tick おきに置くか。
 *
 * 炎はマスごとに進む（10〜11 tick に1マス）。4 tick おきにいまのマスへ光を置くと、
 * 通ったマスに光が残って消えていき、1本の尾に見える。
 */
const TRAIL_EVERY = 4;

/** 落とし穴を踏んだときの画面の揺れ。 */
const PIT_SHAKE = 5;

/**
 * 自律物が消えたときの粒子を出す。
 *
 * ルールの層は、落とし穴を踏んだときに誰がはまったかは返すが、どのマスかは返さない。
 * そこで tick ごとに自律物の顔ぶれを前の tick と比べ、減ったものから見た目を決める。
 *
 * ⚠️ 落とし穴は、仕掛けられたときに何も出さない。見えていると誰も踏まない。
 */
export class ActorEffects {
  #seen = new Set<WorldActor>();
  /** 最後に見た tick。試合が止まっている間は光の跡を足さない。 */
  #lastNow = -1;

  /** 盤面が作り直されたときに呼ぶ。いまある自律物を「前からあったもの」として覚える。 */
  reset(world: Readonly<WorldState>): void {
    this.#seen = new Set(world.actors);
  }

  /**
   * 1 tick ぶんの変化を見て粒子を出す。
   *
   * @returns この tick に起こす画面の揺れ。揺らさないなら 0
   */
  observe(world: Readonly<WorldState>, out: Particle[], rng: CosmeticRng): number {
    let shake = 0;
    const current = new Set(world.actors);
    // ⚠️ 決着のあとの待ちや試合の終わりでは、盤面が止まって時刻が進まない。
    // 時刻だけで間引くと、止まっている間じゅう毎 tick 光を足して白く塗りつぶす。
    const advanced = world.now !== this.#lastNow;
    this.#lastNow = world.now;
    for (const actor of world.actors) {
      if (actor instanceof FoxfireActor && advanced && world.now % TRAIL_EVERY === 0) {
        glow(out, actor.position);
      }
    }
    for (const actor of this.#seen) {
      if (!current.has(actor)) shake = Math.max(shake, this.#vanished(actor, out, rng));
    }
    this.#seen = current;
    return shake;
  }

  /** @returns 画面の揺れ */
  #vanished(actor: WorldActor, out: Particle[], rng: CosmeticRng): number {
    if (actor instanceof FoxfireActor) {
      puff(out, rng, cellOf(actor.position), '#8ce0ff', '💨');
      return 0;
    }
    if (actor instanceof PitActor) {
      // 穴に寿命は無いので、ここで消えたなら誰かが落ちた（ラウンドの作り直しと延長戦の片付けは
      // `reset` で前からあったものとして覚え直すので、ここを通らない）。
      puff(out, rng, actor.cell, '#8a5a2a', '🕳️');
      return PIT_SHAKE;
    }
    return 0;
  }
}
