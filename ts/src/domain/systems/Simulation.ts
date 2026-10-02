import { tick } from '../core/Tick.js';
import type { PlayerInput } from '../input/PlayerInput.js';
import type { PlayerId } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';
import type { SimEvent } from '../events/SimEvent.js';
import { ActionSystem } from './ActionSystem.js';
import { ActorSystem } from './ActorSystem.js';
import { BlastSystem } from './BlastSystem.js';
import { BombSystem } from './BombSystem.js';
import { DamageSystem } from './DamageSystem.js';
import { EffectSystem } from './EffectSystem.js';
import { ItemSystem } from './ItemSystem.js';
import { MovementSystem } from './MovementSystem.js';
import { NegibonSystem } from './NegibonSystem.js';

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
 * ## 起きたことを戻り値で返す
 *
 * この関数は音も鳴らさず画面も触らない。何が起きたかを配列で返すだけで、
 * それをどう扱うかは受け取った側が決める。検証のときは受け取らなければ
 * よく、そのために特別な設定を用意する必要がない。
 */
export class Simulation {
  readonly #actions = new ActionSystem();
  readonly #actors = new ActorSystem();
  readonly #movement = new MovementSystem();
  readonly #negibon = new NegibonSystem();
  readonly #bombs = new BombSystem();
  readonly #blasts = new BlastSystem();
  readonly #items = new ItemSystem();
  readonly #damage = new DamageSystem();
  readonly #effects = new EffectSystem();

  /**
   * 1 tick 進める。
   *
   * @param playerInputs この tick の、プレイヤーごとの入力。
   *   出どころ（キーボード・CPU・通信・記録の再生）は問わない
   */
  step(world: WorldState, playerInputs: ReadonlyMap<PlayerId, PlayerInput>): SimEvent[] {
    const events: SimEvent[] = [];

    // 乗っ取り中の振る舞いを先に進める。位置を決めるのがそちらなので、
    // あとから移動の入力を当てると1 tick ぶん食い違う。
    events.push(...this.#actions.step(world, playerInputs));

    // 動いてから置く。置いてから動く形にすると、置いた瞬間に
    // そのマスから出られてしまい、通り抜けの扱いが1 tick ずれる。
    this.#movement.step(world, playerInputs);
    // 外周の葱ボンは盤面の外を動く。盤面の上の移動とは互いに影響しない。
    events.push(...this.#negibon.step(world, playerInputs));
    events.push(...this.#bombs.step(world, playerInputs));
    events.push(...this.#blasts.step(world));

    // 飛び道具や落とし穴を進める。爆発のあとに置くのは、
    // 爆風で消えるものを同じ tick で処理するため。
    events.push(...this.#actors.step(world));

    // 拾うのは爆発のあと。逆にすると、爆風に焼かれるはずのアイテムを
    // 同じ tick に拾えてしまう。
    events.push(...this.#items.step(world));
    events.push(...this.#damage.step(world));

    this.#effects.step(world);

    // ⚠️ この tick の入力を控えるのは、すべての System が終わったあと。
    // 途中で控えると、後ろの System から見て「押した瞬間」が消える。
    for (const player of world.players) {
      const playerInput = playerInputs.get(player.id);
      if (playerInput !== undefined) player.previousInput = playerInput;
    }

    world.now = tick(world.now + 1);
    return events;
  }
}
