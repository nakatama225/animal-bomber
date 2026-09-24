import { tick } from '../core/Tick.js';
import type { PlayerIntent } from '../intent/PlayerIntent.js';
import type { PlayerId } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';
import { BlastSystem } from './BlastSystem.js';
import { BombSystem } from './BombSystem.js';
import { MovementSystem } from './MovementSystem.js';

/**
 * 試合を1 tick 進める。
 *
 * ## `step()` が経過時間を引数に取らないこと
 *
 * これがこの実装でいちばん目に見える設計判断になっている。原型の
 * `update(dt)` は前のフレームからの経過ミリ秒を受け取り、そこに
 * 倍速スライダーの値まで掛かっていた。結果として、
 * 1回の描画で内部処理が何回まわるかが実行環境によって変わった。
 *
 * 時間が進むのは呼び出し側の1か所だけで、速さは `step()` を
 * **何回呼ぶか**で表す。倍速は回数を増やすだけ、一時停止は
 * 呼ばないだけになる。
 *
 * ## System を並べる順序
 *
 * 下の呼び出しの並びが、そのまま「1 tick の中で何が先に起きるか」の
 * 一覧になる。順序は結果を左右するので、並べ替えるときは
 * 何が変わるかを確かめる。
 *
 * ⚠️ アイテムと被弾は、対応する System ができ次第この並びへ足していく。
 */
export class Simulation {
  readonly #movement = new MovementSystem();
  readonly #bombs = new BombSystem();
  readonly #blasts = new BlastSystem();

  /**
   * 1 tick 進める。
   *
   * @param intents この tick に各プレイヤーが何をしたいか。
   *   出どころ（キーボード・CPU・通信・記録の再生）は問わない
   */
  step(world: WorldState, intents: ReadonlyMap<PlayerId, PlayerIntent>): void {
    // 動いてから置く。置いてから動く形にすると、置いた瞬間に
    // そのマスから出られてしまい、通り抜けの扱いが1 tick ずれる。
    this.#movement.step(world, intents);
    this.#bombs.step(world, intents);
    this.#blasts.step(world);

    // ⚠️ この tick の入力を控えるのは、すべての System が終わったあと。
    // 途中で控えると、後ろの System から見て「押した瞬間」が消える。
    for (const player of world.players) {
      const intent = intents.get(player.id);
      if (intent !== undefined) player.previousIntent = intent;
    }

    world.now = tick(world.now + 1);
  }
}
