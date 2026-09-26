import { secondsToTicks, type Tick } from '../core/Tick.js';

/**
 * サドンデスの決まり。
 *
 * 時間切れの時点で2人以上残っているか、残っていた全員が同じ tick に倒れたとき、
 * 1ラウンドに1回だけ延長戦に入る。引き分けで終わるラウンドを減らすためのもの。
 */

/** 延長戦の長さ。これでも決まらなければ引き分けにする。 */
export const SUDDEN_DEATH_SECONDS = 60;
export const SUDDEN_DEATH_LENGTH: Tick = secondsToTicks(SUDDEN_DEATH_SECONDS);

/**
 * 延長戦の体力（半分の単位。2 で1個ぶん）。
 *
 * 1発で決まるようにする。体力を持ち越すと、延長戦に入る前に守りに徹した
 * 側が有利になる。
 */
export const SUDDEN_DEATH_HP = 2;

/**
 * 延長戦が始まった直後の無敵。
 *
 * 全員を開始位置へ移し、爆弾・火力・靴を上限にする。移った直後は
 * 盤面の様子が一変しているので、つかむまでの間は被弾しないようにする。
 */
export const SUDDEN_DEATH_INVULNERABLE: Tick = secondsToTicks(2.2);
