import type { SimEvent } from '../events/SimEvent.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * プレイヤーに紐づかず、自分で動き続けるもの。
 *
 * 追いかける炎、跳ね回る爆弾、掘られた落とし穴、撒かれた障害物。
 * 出したあとは本人と切り離され、自分の規則で進んで消える。
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
   * 1 tick 進める。
   *
   * @returns 起きたイベントと、役目を終えたかどうか
   */
  readonly tick: (world: WorldState) => { events: SimEvent[]; done: boolean };

  /** 状態の要約に混ぜる値。位置や残り時間など、結果を左右するもの。 */
  readonly encode: () => string;
}
