import type { PlayerState } from '../../domain/state/PlayerState.js';

/**
 * 1人のプレイヤーを描くのに必要なもの。
 *
 * 状態そのものに加えて、描画の側で求めた値（前の tick との間を埋めた位置、
 * いま歩いているか）を持つ。
 */
export interface PlayerView {
  readonly player: PlayerState;
  /** 画面に描く位置（マス単位）。tick の間を埋めてある。 */
  readonly x: number;
  readonly y: number;
  /** 直前の tick で歩いたか。脚を動かすかどうかに使う。 */
  readonly moving: boolean;
  /** いま無敵か（点滅させる）。 */
  readonly invulnerable: boolean;
}
