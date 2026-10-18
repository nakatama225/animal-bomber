import { tick } from '../core/Tick.js';
import type { PlayerInput } from '../input/PlayerInput.js';
import type { PlayerId } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';
import type { SimEvent } from '../events/SimEvent.js';
import { ActionSystem } from './ActionSystem.js';
import { ActorSystem } from './ActorSystem.js';
import { AutobombSystem } from './AutobombSystem.js';
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
 * 並びは原型の update（`legacy/animal-bomber.html`）と同じにしてある。
 *
 * 1. プレイヤーごとに：焼けた舌を戻す → 一時的な状態の時間を減らす → 乗っ取り中の振る舞いを
 *    進める → 「勝手に設置」の拍を見る（原型の「効果タイマー」の輪）
 * 2. プレイヤーごとに：動く → ボタンの爆弾を置く → 技のボタンを見る → 足元のアイテムを拾う
 *    （原型の「入力 / AI」の輪。外周のプレイヤーは外周を動いて葱を撃つ）
 * 3. 爆弾の通り抜けを外す → 盤面の物を進める（落とし穴 → 葱 → 追いかける炎 → 撒く本体 →
 *    跳ねる爆弾の順）
 * 4. 溶けきったもの・残る長さを過ぎたアイテムを消す
 * 5. 導火線を進め、尽きた爆弾を連鎖ごと爆発させる（跳ねる爆弾が 3. で生やした導火線 0 の爆弾も、ここで
 *    `world.bombs` の並びの順に爆発する。原型も同じ update の爆弾の輪で起こす）
 * 6. 爆風の残り時間を進める
 * 7. 爆風に触れたプレイヤーの体力を減らす → 爆風に触れた振る舞い（伸びている舌）を終える
 * 8. 外周を閉じる時刻なら閉じる（原型の update の最後の checkEnd の頭。`NegibonSystem.closeIfDue`）
 *
 * 1. と 2. をプレイヤーごとに回すので、番号の小さいプレイヤーが置いた爆弾は、同じ tick に動く
 * 番号の大きいプレイヤーの壁になる。拾うのが爆発より先なので、爆発する tick に踏み込んだ
 * アイテムは焼ける前に拾える。落とし穴に落ちるのも拾ったあと（穴が滑りを消すので、穴の上の
 * バナナを踏んでも、穴を抜けたあと滑らない）。どれも原型と同じ。
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
  readonly #autobomb = new AutobombSystem();
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

    // 1. 乗っ取り中の振る舞いを先に進める。位置を決めるのがそちらなので、
    // あとから移動の入力を当てると1 tick ぶん食い違う。
    // 「勝手に設置」は、そのプレイヤーの振る舞いを進めた直後に置く（`AutobombSystem` の説明）。
    for (const player of world.players) {
      events.push(...this.#actors.stepOwnedBy(world, player));
      this.#effects.advanceFor(player);
      events.push(...this.#actions.advanceFor(world, player, playerInputs.has(player.id)));
      events.push(...this.#autobomb.step(world, player));
    }

    // 2. 動く → ボタンの爆弾 → 技を始める → 拾う、を1人ずつ済ませる。
    // ボタンの爆弾は動いてから置く。置いてから動く形にすると、置いた瞬間に
    // そのマスから出られてしまい、通り抜けの扱いが1 tick ずれる。
    for (const player of world.players) {
      const playerInput = playerInputs.get(player.id);
      // 外周の葱ボンは盤面の外を動く。盤面の上の処理とは互いに影響しない。
      events.push(...this.#negibon.stepFor(world, player, playerInput));
      if (playerInput !== undefined) {
        this.#movement.moveFor(world, player, playerInput);
        events.push(...this.#bombs.placeFor(world, player, playerInput));
        // 振る舞いの最中も見る。終わった tick のうちに押せば次の技が出る（`ActionSystem` の説明）。
        events.push(...this.#actions.watchFor(world, player, playerInput));
      }
      events.push(...this.#items.pickUpFor(world, player));
    }

    // 3. 盤面の物を進める（種類ごとの順。`WorldActor.turn`）。
    this.#bombs.releasePassThrough(world);
    events.push(...this.#actors.step(world));

    // 4〜6.
    events.push(...this.#items.expire(world));
    this.#bombs.advanceFuses(world);
    events.push(...this.#blasts.detonateExpired(world));
    this.#blasts.expireBlasts(world);

    // 7. 伸びている舌は、被弾を見たあとに焼けたかを見る（爆風が出た tick のうちに焼き切れる）。
    events.push(...this.#damage.step(world));
    events.push(...this.#actions.afterDamage(world));

    // 8. 外周を閉じるのは最後（原型の L4405 → L4411 と同じ位置）。閉じる tick の中でも、外周のプレイヤーは 2. で
    // 動いて撃ち、葱は 3. で当たる。閉じたあとに `GameSession` がラウンドの決着を見る（原型の checkEnd も、
    // 外周を閉じてから盤面に残ったプレイヤーを数える）。
    events.push(...this.#negibon.closeIfDue(world));

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
