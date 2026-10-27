import type { SimEvent } from '../../domain/events/SimEvent.js';
import type { WorldState } from '../../domain/state/WorldState.js';

/**
 * 横の板の名札と時計を、いつ作り直すか（原型の `renderCards` を呼ぶ時。Python 版の `refreshes_panel` と同じ形）。
 *
 * 原型は名札と時計を、試合の時間で 0.25 秒ごとに作り直す（`G.elapsed%0.25<dt`。L4406。`G.elapsed` はラウンドの
 * 頭で 0 になり、ポーズと幕の間は進まない）。この版は盤面の時刻（`world.now`）で数え、15 tick の区切りを越えた
 * ときに作り直す。区切りの間に替わった中身（落とし穴の残り秒・体力など）は、次の区切りまで出ない（原型と同じ）。
 *
 * 4 Hz を待たずに作り直す場面は、原型が `renderCards` をすぐ呼ぶ所（`refreshesPanel`）と、ラウンドの始まり
 * （盤面が替わったとき。L4158）。ポーズの切り替えとゲームの速さでは作り直さない（原型も呼ばない。キーの案内・
 * ポーズのボタンの字・つまみだけを替える。L4217-4221・L6049-6052）。
 *
 * 盤面の時刻で数えるので、ゲームの速さを変えると、実時間の間隔も原型と同じく変わる（3 倍で約 83 ms）。
 */

/** 名札と時計を作り直す間隔（tick。原型の 0.25 秒）。 */
export const PANEL_REFRESH_TICKS = 15;

/**
 * 名札と時計をすぐ作り直すイベントか。
 *
 * 原型が 4 Hz を待たずに `renderCards` を呼ぶ場面：被弾（L1668）・外周へ回った（L2270）・入れ替わった（L2355）・
 * 外周が閉じた（L2362）・舌が焼き切れた（L2489）・穴を掘り終えた（L2578）・落とし穴にはまった（L2598）・
 * とくぎを使った（L2627）・舌が戻った（L4308）・延長戦（L4464）・決着（L4510）。
 */
export function refreshesPanel(event: SimEvent): boolean {
  switch (event.type) {
    case 'playerHurt':
    case 'playerDown':
    case 'revived':
    case 'lanesClosed':
    case 'burntOff':
    case 'reachRestored':
    case 'suddenDeath':
    case 'roundEnded':
      return true;
    case 'techniqueUsed':
      return event.special;
    case 'techniqueMoment':
      return event.moment === 'pitDug';
    case 'effectApplied':
      return event.effect === 'pitfall';
    default:
      // ほかのイベントは、名札の中身を約 4 Hz の作り直しで出す（原型と同じ）。
      return false;
  }
}

/** 名札と時計を作り直す時を数える。試合ごと（通信対戦は次の試合ごと）に作る。 */
export class PanelRefresh {
  /** 最後に作り直したときの盤面。替わったら（ラウンドの始まり）すぐ作り直す。 */
  #world: Readonly<WorldState> | null = null;
  /** 最後に作り直したときの区切りの番号（`world.now` を `PANEL_REFRESH_TICKS` で割って切り捨てたもの）。 */
  #slot = 0;
  /** すぐ作り直すイベントを、まだ写していないか。 */
  #pending = false;

  /** tick を進めるたびに、その tick のイベントを渡す。 */
  observe(events: readonly SimEvent[]): void {
    if (events.some(refreshesPanel)) this.#pending = true;
  }

  /**
   * イベントに載らない理由で、次に描くときに作り直す。通信対戦で、抜けたプレイヤーを CPU が引き継いで名札の札が替わった
   * とき（原型は `peer_left` を受けた場で `renderCards` を呼ぶ。L3793）。
   */
  request(): void {
    this.#pending = true;
  }

  /**
   * 描くときに呼ぶ。いま名札と時計を作り直すか。
   *
   * 作り直すと答えたら、作り直したものとして数える（同じ区切りの中では、次のイベントか区切りまで作り直さない）。
   */
  due(world: Readonly<WorldState>): boolean {
    const slot = Math.floor(world.now / PANEL_REFRESH_TICKS);
    const due = world !== this.#world || slot !== this.#slot || this.#pending;
    this.#world = world;
    this.#slot = slot;
    this.#pending = false;
    return due;
  }
}
