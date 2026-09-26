import { secondsToTicks, type Tick } from '../core/Tick.js';
import { ROUND_SECONDS, WINS_TO_TAKE_MATCH } from './tuning.js';

/** 1試合ぶんの設定。ロビーで決めて、始まったら変えない。 */
export interface MatchConfig {
  /** 1ラウンドの制限時間。 */
  readonly roundLimit: Tick;
  /** 何勝で試合を取るか。 */
  readonly winsToTake: number;
  /** 決着がつかないとき、1回だけ延長戦（サドンデス）に入るか。切ると引き分けにする。 */
  readonly suddenDeath: boolean;
  /** 各プレイヤーの初期体力（半分の単位。6 で3個ぶん）。 */
  readonly startingHp: number;
  /**
   * 盤面と抽選に使う種。
   *
   * 試合ごとに1つ持ち、ラウンドが変わるたびにここから導いた種を使う。
   * 「ラウンド2の盤面」も設定から決まるため、試合全体が再現できる。
   */
  readonly seed: number;
  /** 参加する動物。プレイヤー番号の順。 */
  readonly animals: readonly string[];
}

/** 既定の設定。 */
export function defaultMatchConfig(seed: number, animals: readonly string[]): MatchConfig {
  return {
    roundLimit: secondsToTicks(ROUND_SECONDS),
    winsToTake: WINS_TO_TAKE_MATCH,
    suddenDeath: true,
    startingHp: 6,
    seed,
    animals,
  };
}

/**
 * そのラウンドで使う種を、試合の種とラウンド番号から導く。
 *
 * ラウンドごとに違う盤面にしつつ、試合全体は1つの種から再現できる。
 * 乗算と加算だけで作っているのは、実行環境をまたいでも同じ値になるため。
 */
export function seedForRound(config: MatchConfig, round: number): number {
  return (config.seed + round * 0x9e3779b1) >>> 0;
}
