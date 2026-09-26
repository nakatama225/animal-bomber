import type { SimEvent } from '../../domain/events/SimEvent.js';
import type { PlayerId } from '../../domain/state/PlayerState.js';
import type { WorldState } from '../../domain/state/WorldState.js';

interface Snapshot {
  readonly x: number;
  readonly y: number;
  readonly walked: number;
}

/**
 * 1つ前の tick のプレイヤーの位置を覚えておく。
 *
 * 画面の書き換えは tick と同じ間隔とは限らない。tick の間に描くときは、
 * 前の tick と今の tick の間を埋めた位置に描くと動きが滑らかになる。
 *
 * ⚠️ 間を埋めるのは描画だけ。ルールの層の位置は tick ごとにしか変わらない。
 */
export class PositionHistory {
  #world: Readonly<WorldState> | null = null;
  readonly #before = new Map<PlayerId, Snapshot>();

  /** tick を進める直前に呼ぶ。 */
  capture(world: Readonly<WorldState>): void {
    this.#world = world;
    for (const player of world.players) {
      this.#before.set(player.id, {
        x: player.position.x,
        y: player.position.y,
        walked: player.walked,
      });
    }
  }

  /**
   * 1つ前の tick の状態。
   *
   * ラウンドが変わって盤面が作り直された直後は、前の盤面の位置から
   * 新しい開始位置まで線を引いてしまわないよう、何も返さない。
   */
  before(world: Readonly<WorldState>, id: PlayerId): Snapshot | undefined {
    if (world !== this.#world) return undefined;
    return this.#before.get(id);
  }

  /**
   * tick を進めた直後に、起きたイベントを渡す。
   *
   * 歩いたのではなく飛び移ったプレイヤーは、1つ前の位置を捨てる。次に控えを取るまで、
   * いまの位置にそのまま描く。間を埋めると、盤面を横切って滑っていくように見える。
   */
  onEvents(events: readonly SimEvent[], world: Readonly<WorldState>): void {
    for (const event of events) {
      // 延長戦では、加わる全員が開始位置へ移る。
      if (event.type === 'suddenDeath') {
        for (const player of world.players) this.#before.delete(player.id);
      }
      // 葱で戻った人は、外周から当てた相手の位置へ移る。
      if (event.type === 'revived') this.#before.delete(event.player);
    }
  }
}
