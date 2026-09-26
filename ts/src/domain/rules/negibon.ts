import { secondsToTicks, TICKS_PER_SECOND, type Tick } from '../core/Tick.js';

/**
 * 葱ボンの決まり。
 *
 * 倒れたプレイヤーは、残り時間があれば盤面の外周へ回り、外周の帯の上を
 * 動きながら盤面へ葱を撃つ。盤面にいる相手に当てると入れ替わり、撃った側が
 * 当てた相手の位置で盤面へ戻る。倒れたあとも試合に関わり続けられる仕組み。
 */

/**
 * 残り時間がこれ以下になったら、外周の葱ボンは全員退場する。以後に倒れた人も
 * 外周へ回らない。終盤まで入れ替わりが続くと、決着がつかない。
 */
export const NEGIBON_CUTOFF: Tick = secondsToTicks(60);

/** 外周を回る速さ（マス毎秒）。 */
export const LANE_SPEED_PER_SECOND = 5.5;
export const LANE_SPEED = LANE_SPEED_PER_SECOND / TICKS_PER_SECOND;

/**
 * 外周の帯の幅（マス）。葱ボンは帯の真ん中に立ち、そこから葱が飛び出す。
 *
 * 帯は盤面の外側に描く。1マスまるごとの幅にすると、画面の余白が目立つので
 * 細くしてある。葱が飛ぶ距離は帯の真ん中から数えるので、射程にも効く。
 */
export const LANE_WIDTH = 0.62;

/** 葱を撃つ間隔。短いと、外周と盤面の入れ替わりが止まらない。 */
export const LEEK_COOLDOWN: Tick = secondsToTicks(3);

/** 外周へ回った直後に撃てるようになるまでの長さ。倒れた直後の撃ち返しを遅らせる。 */
export const LEEK_FIRST_COOLDOWN: Tick = secondsToTicks(3.5);

/** 葱が飛ぶ速さ（マス毎秒）。遅いほど避けやすい。 */
export const LEEK_SPEED_PER_SECOND = 6.5;
export const LEEK_SPEED = LEEK_SPEED_PER_SECOND / TICKS_PER_SECOND;

/**
 * 葱が届く距離（マス）。盤面の中央までは届かない。
 * 端から端まで届くと、葱ボンのいる列がずっと危ない場所になる。
 */
export const LEEK_RANGE = 6;

/** 葱が消えるまでの長さ。射程のほうが先に尽きるので、止まった葱の後始末に当たる。 */
export const LEEK_LIFETIME: Tick = secondsToTicks(3);

/**
 * 葱が当たったとみなす、中心どうしの縦・横のずれ（マス）。
 * 甘いと、同じ列にいるだけで必ず当たる。
 */
export const LEEK_HIT = 0.28;

/**
 * 盤面へ戻ったときの体力（半分の単位。2 で1個ぶん）。
 * 満タンで戻すと入れ替わりが止まらず、引き分けが増える。
 */
export const REVIVE_HP = 2;

/** 盤面へ戻った直後の無敵。戻った瞬間に葱で撃ち返されるのを防ぐ。 */
export const REVIVE_INVULNERABLE: Tick = secondsToTicks(2.4);
