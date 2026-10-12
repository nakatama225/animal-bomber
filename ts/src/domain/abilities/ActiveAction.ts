import type { SimEvent } from '../events/SimEvent.js';
import type { PlayerState } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * プレイヤーを一時的に乗っ取る振る舞い。
 *
 * 突進・穴掘り・舌のばしのように、始まってから終わるまで
 * **自前の規則で動くもの**を表す。移動・爆弾・技のボタンを受け付けるかは、
 * 下の性質（`drivesMovement`・`canPlaceBomb`・`blocksButtons`）が決める（いまの動物の振る舞いはどれも
 * 移動を決め、爆弾を置けない。性質を分けてあるのは、そうでない技を足すため）。
 *
 * 最中も技のボタンは見る（原型と同じ）。舌の間は通常技もとくぎも出ない。突進中は鼻水を吹け、
 * とくぎのボタンでは突進が最初からやり直しになる（抱えていた悪いアイテムは撒かれずに消える）。
 * 掘っている間は、押すとチキンだけ減る。どれも動物ごとの能力（`Ability`）の側が決め、
 * `ActionSystem` はこの性質を見るだけ。
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
 * 各 System が見るのは下の6つの性質だけで、**何の振る舞いかは見ない**。
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
   * 葱が当たらない状態か（`isUntouchable`。原型の isUntouchable と同じく、葱だけが見る）。
   *
   * ⚠️ 爆風・追いかける炎・体当たりの傷が当たるかとは別。突進は「葱は当たらないが、爆風も
   * 追いかける炎も、ほかの突進の体当たりも当たる」（傷は `damageCap` で減る）。
   * この2つを1つの真偽値にまとめると、どちらかの挙動が必ず壊れる。
   */
  readonly untouchable: boolean;

  /** 爆弾を置けるか。 */
  readonly canPlaceBomb: boolean;

  /**
   * true の間、技のボタンを押しても通常技もとくぎも出ない（原型の doAction・doSpecial の
   * `if (p.tongue) return;`）。押した長さは数え続け、しきい値に届けばその押し方のとくぎはそれきりになる。
   */
  readonly blocksButtons: boolean;

  /**
   * true の間、足元のアイテムをふつうの拾い（`ItemSystem`）では拾わない。通り道のアイテムは
   * この振る舞いが自分で扱う。
   *
   * ⚠️ 自分で扱う振る舞いがふつうの拾いも通すと、自分の拾いのあとに同じ tick のうちに
   * 足元へ来たアイテム（ほかの振る舞いが撒いた・押しのけられた先にあった）を、
   * 自分の扱い方を通さずにそのまま効かせてしまう。原型も、突進の最中だけふつうの拾いを
   * 飛ばしていた（update の `if (!p.effects.charge) pickupCheck(p);`）。
   */
  readonly sweepsItems: boolean;

  /**
   * 1 tick 進める。
   *
   * @returns 起きたイベントと、終わったかどうか
   */
  readonly tick: (world: WorldState, player: PlayerState) => { events: SimEvent[]; done: boolean };

  /**
   * 終わるときの後始末。
   *
   * 途中で打ち切られた場合も呼ばれる。抱えているものを置く、
   * といった処理をここに書く。
   */
  readonly finish?: (world: WorldState, player: PlayerState) => SimEvent[];

  /**
   * 被弾を見たあと（1 tick の最後）に、爆風に触れたかを見る。触れて終わるなら done を true にする
   * （終わったら `finish` も呼ばれる）。
   *
   * 爆風が出た tick のうちに見るため、`tick` とは別にしてある（原型も、被弾を見た直後に
   * 伸びている舌が焼けたかを見る）。
   */
  readonly afterDamage?: (world: WorldState, player: PlayerState) => { events: SimEvent[]; done: boolean };
}
