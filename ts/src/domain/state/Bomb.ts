import type { Cell } from '../core/Coord.js';
import type { EntityId } from '../core/EntityId.js';
import type { Tick } from '../core/Tick.js';
import type { PlayerId } from './PlayerState.js';

/** 盤面に置かれた爆弾。 */
export interface Bomb {
  readonly id: EntityId;
  readonly cell: Cell;
  readonly owner: PlayerId;
  /** 爆風が各方向へ届くマス数。置いた時点の持ち主の火力で決まる。 */
  readonly power: number;
  /** 爆発までの残り tick。 */
  fuse: Tick;
  /**
   * このマスからまだ降りていないプレイヤー。降りるまで通り抜けられる。
   *
   * ⚠️ 置いた本人だけを通す形にすると、他人に足元へ置かれた側が
   * その場から動けなくなる。置かれた瞬間に重なっている全員を入れる。
   */
  readonly passThrough: Set<PlayerId>;
  /** 誘爆の連鎖に取り込まれたか。同じ爆弾を二度数えないための印。 */
  chained: boolean;
}

/** 爆風が乗っている1マス。 */
export interface Blast {
  readonly id: EntityId;
  readonly cell: Cell;
  /** この爆風を出した爆弾の持ち主。誰に倒されたかの判定に使う。 */
  readonly owner: PlayerId;
  /** 爆弾が置かれていたマスか。まわりへ伸びたぶんは false。 */
  readonly isCenter: boolean;
  /** 消えるまでの残り tick。 */
  remaining: Tick;
}
