import { tick } from '../core/Tick.js';
import type { PlayerIntent } from '../intent/PlayerIntent.js';
import type { PlayerId } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';
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
 * ⚠️ 現在は移動のみ。爆弾・爆風・アイテム・被弾は、
 * 対応する System ができ次第この並びへ足していく。
 */
export class Simulation {
  readonly #movement = new MovementSystem();

  /**
   * 1 tick 進める。
   *
   * @param intents この tick に各プレイヤーが何をしたいか。
   *   出どころ（キーボード・CPU・通信・記録の再生）は問わない
   */
  step(world: WorldState, intents: ReadonlyMap<PlayerId, PlayerIntent>): void {
    this.#movement.step(world, intents);

    world.now = tick(world.now + 1);
  }
}
