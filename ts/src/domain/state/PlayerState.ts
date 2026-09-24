import type { Direction, Point } from '../core/Coord.js';
import type { Tick } from '../core/Tick.js';
import { BASE_SPEED, MAX_SPEED, SHOE_STEP } from '../rules/tuning.js';

/** プレイヤーの席番号。0 から 3。 */
export type PlayerId = 0 | 1 | 2 | 3;

/** すべての席番号を、いつも同じ順で並べたもの。 */
export const PLAYER_IDS: readonly PlayerId[] = [0, 1, 2, 3];

/** プレイヤーの生死。 */
export type LifeState = 'alive' | 'dead';

/**
 * プレイヤー1人ぶんの状態。
 *
 * ⚠️ 体力は**半分の単位を整数で**持つ。`2` が1個ぶんで、`1` が半分。
 * 小数で持たないのは、Python 版と揃えるためでもある。Python の `round` は
 * 偶数丸めなので、小数を丸める処理を入れると言語をまたいで結果が食い違う。
 * 整数で持てばその問題そのものが起きない。
 */
export interface PlayerState {
  readonly id: PlayerId;
  /** 動物の種類。content 層のデータを引くための鍵。 */
  readonly animal: string;

  /** 盤面上の位置（マス単位の連続座標）。 */
  position: Point;
  /** 向いている方向。爆風や技の向きに使う。 */
  facing: Direction;

  life: LifeState;
  /** 体力。半分の単位の整数で持つ。 */
  hp: number;

  /** 靴を取った段数。 */
  shoes: number;
  /** 爆風の届くマス数。 */
  power: number;
  /** 同時に置ける爆弾の数。 */
  maxBombs: number;
  /** いま盤面に出ている自分の爆弾の数。 */
  activeBombs: number;

  /** 無敵が切れる tick。それまでは被弾しない。 */
  invulnerableUntil: Tick;

  /** 歩いた距離の合計。歩行の見た目にだけ使う。 */
  walked: number;
}

/**
 * そのプレイヤーの、1 tick あたりの移動距離（マス）。
 *
 * 靴の段数だけ速くなり、上限で頭打ちになる。
 */
export function speedOf(player: PlayerState): number {
  return Math.min(MAX_SPEED, BASE_SPEED + player.shoes * SHOE_STEP);
}

/** 無敵の最中か。 */
export function isInvulnerable(player: PlayerState, now: Tick): boolean {
  return now < player.invulnerableUntil;
}

/** 状態を複製する。試算に使う。 */
export function clonePlayer(player: PlayerState): PlayerState {
  return { ...player, position: { ...player.position } };
}
