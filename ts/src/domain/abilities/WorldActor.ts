import type { SimEvent } from '../events/SimEvent.js';
import type { PlayerId } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 盤面の物を進める順の値（小さいほど先）。原型の update が、プレイヤーを動かしたあとに回す順。
 *
 * 跳ねる爆弾の爆発と、落とし穴に落ちるのは、ふつうの爆弾の導火線より先（原型も同じ）。
 */
export const ACTOR_TURNS = {
  pit: 0,
  leek: 1,
  chaser: 2,
  scatter: 3,
  slime: 4,
} as const;

/**
 * プレイヤーに紐づかず、自分で動き続けるもの。
 *
 * 追いかける炎、跳ね回る爆弾、掘られた落とし穴、撒く本体、焼けた舌。
 * 出したあとは出したプレイヤーと切り離され、自分の規則で進んで消える。
 *
 * `ActiveAction`（プレイヤーを乗っ取る振る舞い）と形を揃えてある。
 * 違いは「誰のものか」だけで、どちらも
 * **System は種類を知らず、`tick` を呼んで終わりを待つ**。
 *
 * 動物を追加して新しい飛び道具が増えても、`ActorSystem` には
 * 1行も足さない。
 */
export interface WorldActor {
  /** 記録と表示のための名前。System はこれで分岐しない。 */
  readonly kind: string;

  /**
   * 1 tick の中で、いつ進めるか（原型の update の並びに合わせる）。
   *
   * - 数のとき … プレイヤーが全員動き終わったあとに、数の小さい順に進める。同じ数どうしは
   *   出た順。原型は種類ごとに順を決めて回す（落とし穴 → 葱 → 追いかける炎 → 撒く本体 →
   *   跳ねる爆弾）。いまの値は `ACTOR_TURNS`
   * - `'owner'` のとき … 持ち主のプレイヤーの番に、状態の時間を減らす前に進める（焼けた舌が
   *   戻るのは、原型ではプレイヤーごとの効果の処理の中）。`owner` を持つものだけ
   */
  readonly turn: number | 'owner';

  /** 出したプレイヤー。`turn` が `'owner'` のものは、このプレイヤーの番に進める。 */
  readonly owner: PlayerId;

  /**
   * 1 tick 進める。
   *
   * @returns 起きたイベントと、役目を終えたかどうか
   */
  readonly tick: (world: WorldState) => { events: SimEvent[]; done: boolean };

  /** 状態の要約に混ぜる値。位置や残り時間など、結果を左右するもの。 */
  readonly encode: () => string;
}
