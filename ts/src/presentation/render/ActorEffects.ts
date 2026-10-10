import type { WorldActor } from '../../domain/abilities/WorldActor.js';
import { FoxfireActor } from '../../domain/abilities/fox/FoxfireActor.js';
import { PitActor } from '../../domain/abilities/mole/PitAction.js';
import { ScatteredActor } from '../../domain/abilities/rabbit/ScatterAction.js';
import { cellOf } from '../../domain/core/Coord.js';
import type { WorldState } from '../../domain/state/WorldState.js';
import type { CosmeticRng } from '../CosmeticRng.js';
import { glow, puff, type Particle } from './particles.js';

/**
 * 追いかける炎の通った跡を、何 tick おきに置くか。
 *
 * 炎は 1 tick に 0.17 マス進むので、4 tick おきでおよそ 0.7 マス間隔になる。
 * 光の玉の半径は 0.52 マスあり、この間隔なら玉どうしが重なって1本の尾に見える。
 */
const TRAIL_EVERY = 4;

/** 落とし穴を踏んだときの画面の揺れ。 */
const PIT_SHAKE = 5;

/**
 * 自律物が現れた・消えたときの粒子を出す。
 *
 * ルールの層は、撒かれた障害物が置かれたことをイベントで返さない。落とし穴や
 * 障害物を踏んだときも、誰に効いたかは返すが、どのマスかは返さない。
 * そこで tick ごとに自律物の顔ぶれを前の tick と比べ、増えたもの・減ったものから
 * 見た目を決める。
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
      if (!this.#seen.has(actor)) this.#appeared(actor, out, rng);
    }
    for (const actor of this.#seen) {
      if (!current.has(actor)) shake = Math.max(shake, this.#vanished(actor, out, rng));
    }
    this.#seen = current;
    return shake;
  }

  #appeared(actor: WorldActor, out: Particle[], rng: CosmeticRng): void {
    if (actor instanceof ScatteredActor) puff(out, rng, actor.cell, '#f7a8c4', '💩');
  }

  /** @returns 画面の揺れ */
  #vanished(actor: WorldActor, out: Particle[], rng: CosmeticRng): number {
    if (actor instanceof ScatteredActor) {
      // 残り時間があるうちに消えたなら、誰かが踏んだ。
      if (actor.remaining > 0) puff(out, rng, actor.cell, '#b98a5a', '💩');
      else puff(out, rng, actor.cell, '#f7a8c4', '💨');
      return 0;
    }
    if (actor instanceof FoxfireActor) {
      puff(out, rng, cellOf(actor.position), '#8ce0ff', '💨');
      return 0;
    }
    if (actor instanceof PitActor) {
      // 時間切れで消えた穴は、最後まで見せない。誰かが落ちたときだけ出す。
      // 落ちたかは残り時間で見分ける（踏まれた tick には残りを減らさない。`PitActor.tick`）。
      // そのマスに誰かがいるかで見分けると、落ちない相手（掘れる動物・はまっている最中の
      // プレイヤー）が乗ったまま時間切れになったとき、穴の位置を見せてしまう。
      if (actor.remaining <= 0) return 0;
      puff(out, rng, actor.cell, '#8a5a2a', '🕳️');
      return PIT_SHAKE;
    }
    return 0;
  }
}
