import type { SimEvent } from '../events/SimEvent.js';
import type { PlayerState } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * プレイヤーを一時的に乗っ取る振る舞い。
 *
 * 突進・穴掘り・舌のばしのように、始まってから終わるまで
 * **本人の操作を受け付けず、自前の規則で動くもの**を表す。
 *
 * ## `EffectBag` と分けてある理由
 *
 * 「超スロー」や「爆弾おけない」は、既存の処理に**倍率や可否を与える**
 * だけなので、値として持てば済む。一方こちらは、移動そのものを
 * 差し替え、ブロックを壊し、当たり判定を変える。性質が違う。
 *
 * これを同じ袋に入れて `if (effects.has('charge')) return;` と書くと、
 * 移動・爆弾・被弾・アイテムのそれぞれに種類ごとの分岐が生えていく。
 * 原型では突進の判定だけで 11 箇所に散っていた。
 *
 * ## System は種類を知らない
 *
 * 各 System が見るのは下の4つの性質だけで、**何の振る舞いかは見ない**。
 * 動物を追加しても `src/domain/systems/` には1行も足さない。
 * これが守られているかは `tests/boundary/guards.test.ts` が見張る。
 */
export interface ActiveAction {
  /** 記録と表示のための名前。System はこれで分岐しない。 */
  readonly kind: string;

  /** true の間、移動の入力を受け付けない（この振る舞いが位置を決める）。 */
  readonly drivesMovement: boolean;

  /**
   * 受けるダメージの上限。null なら軽減しない。
   *
   * ⚠️ 突進は「止まらないがダメージは受ける」。0 にはしない。
   * 無敵にすると、突進を撃ち続けるだけで勝ててしまう。
   */
  readonly damageCap: number | null;

  /**
   * 体当たりや飛び道具が当たらない状態か。
   *
   * ⚠️ 爆風が当たるかどうかとは別。突進は「当たり判定は消えるが
   * 爆風は通る」。この2つを1つの真偽値にまとめると、
   * どちらかの挙動が必ず壊れる。
   */
  readonly untouchable: boolean;

  /** 爆弾を置けるか。 */
  readonly canPlaceBomb: boolean;

  /**
   * 1 tick 進める。
   *
   * @returns 起きたイベントと、終わったかどうか
   */
  tick(world: WorldState, player: PlayerState): { events: SimEvent[]; done: boolean };

  /**
   * 終わるときの後始末。
   *
   * 途中で打ち切られた場合も呼ばれる。抱えているものを置く、
   * といった処理をここに書く。
   */
  finish?(world: WorldState, player: PlayerState): SimEvent[];
}
