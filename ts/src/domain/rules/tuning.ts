/**
 * ゲームの手触りを決める数値。
 *
 * **値の横に「なぜこの値か」を書く。** 理由のない数値は、次に読んだ人が
 * 「とりあえず置いた値」と判断して自由に変えます。原型の開発ノートで
 * いちばん価値があったのはこの部分だったので、値と一緒に移してあります。
 *
 * 秒で書いてある設定は、ここで tick 数へ直したものも合わせて持ちます。
 * 読むときは秒のほうが分かりやすく、計算に使うのは tick のほうなので、
 * 変換をここ1か所に閉じ込めます。
 */

import { secondsToTicks, TICKS_PER_SECOND, type Tick } from '../core/Tick.js';

/* ------------------------------------------------------------------ 盤面 */

/**
 * 外周の壁を含むマス数。
 *
 * 本家（15×13）より目を細かくしてある。狭いと開始直後に相手と出会ってしまい、
 * アイテムを拾って強くなる時間が生まれない。
 */
export const COLS = 23;
export const ROWS = 17;

/**
 * 壊せるブロックが置かれる密度。
 *
 * 空いているマスのうちこの割合を埋める。低いと見通しがよくなり、
 * 開始直後から撃ち合いになる。
 */
export const SOFT_BLOCK_RATIO = 0.78;

/** プレイヤーの開始位置。盤面の四隅。 */
export const SPAWN_CELLS = [
  { col: 1, row: 1 },
  { col: COLS - 2, row: 1 },
  { col: 1, row: ROWS - 2 },
  { col: COLS - 2, row: ROWS - 2 },
] as const;

/* ------------------------------------------------------------------ 移動 */

/**
 * 基本の移動速度（1秒あたりのマス数）。
 *
 * 盤面が 23×17 と広いので、端から端まで移動するのに数秒かかる速さにしてある。
 */
export const BASE_SPEED_PER_SECOND = 3.7;

/** 1 tick あたりの移動距離（マス）。 */
export const BASE_SPEED = BASE_SPEED_PER_SECOND / TICKS_PER_SECOND;

/**
 * 靴のアイテム1個で上がる速度（1秒あたりのマス数）。
 *
 * 取れる段数を増やしたぶん、1段の上がり幅を小さくしてある。
 */
export const SHOE_STEP_PER_SECOND = 0.42;
export const SHOE_STEP = SHOE_STEP_PER_SECOND / TICKS_PER_SECOND;

/**
 * 速度の上限（1秒あたりのマス数）。
 *
 * 靴を上限の 13 段まで取ると 3.7 + 13 × 0.42 = 9.16 になるので、
 * その少し上に置いてある。
 *
 * ⚠️ この値を上げると、1回の内部処理で進む距離が伸びて壁や爆風を
 * すり抜ける。移動を細かく分ける回数はこの最高速から決めているため、
 * 上げるならそちらも合わせて直す。
 */
export const MAX_SPEED_PER_SECOND = 9.4;
export const MAX_SPEED = MAX_SPEED_PER_SECOND / TICKS_PER_SECOND;

/**
 * 当たり判定に使うプレイヤーの半径（マス）。
 *
 * 0.5 より小さいので、通路の中央に乗っていれば壁に触れない。
 */
export const PLAYER_RADIUS = 0.36;

/**
 * 通路への吸い付きを止める距離（マス）。
 *
 * 曲がり角で通路の中央からわずかにずれていると引っかかるため、
 * 進行方向と直角に寄せる。これ以上近ければ寄せ終わりとみなす。
 */
export const ALIGN_EPSILON = 0.004;

/** 移動できたときの、寄せ幅にかける倍率。まっすぐ進むほうを優先する。 */
export const ALIGN_RATE_WHEN_MOVING = 0.9;

/**
 * 1 tick の移動を何回に分けるか、を決める基準距離（マス）。
 *
 * 最高速で 1 tick に進む距離をこの値で割った回数だけ、当たり判定を挟む。
 * 分けないと、速いときに薄い壁をすり抜ける。
 *
 * ⚠️ 分けるのは**移動の当たり判定だけ**。原型では導火線の進みも
 * 入力の読み取りも同じループで分けていたため、倍速にすると
 * 1回のキー入力が2〜3回として処理される不具合が出た。
 */
export const MOVE_SUBSTEP_DISTANCE = 0.12;

/* ------------------------------------------------------------------ 爆弾 */

/** 置いてから爆発するまで（秒）。 */
export const BOMB_FUSE_SECONDS = 2.4;
export const BOMB_FUSE: Tick = secondsToTicks(BOMB_FUSE_SECONDS);

/** 爆風が残る時間（秒）。 */
export const BLAST_DURATION_SECONDS = 0.46;
export const BLAST_DURATION: Tick = secondsToTicks(BLAST_DURATION_SECONDS);

/** 被弾したあとの無敵時間（秒）。 */
export const INVULNERABLE_SECONDS = 1.25;
export const INVULNERABLE: Tick = secondsToTicks(INVULNERABLE_SECONDS);

/** 爆風の届く初期のマス数。 */
export const BASE_POWER = 1;

/**
 * 爆風の届く上限。
 *
 * 盤面が 23×17 と広いため、8 では火力が足りなかった。
 */
export const MAX_POWER = 13;

/** 同時に置ける爆弾の上限。 */
export const MAX_BOMBS = 13;

/** 靴で上げられる段数の上限。 */
export const MAX_SHOES = 13;

/**
 * 爆風の当たり判定（マス）。
 *
 * 移動の判定（0.36）より小さい。同じにすると、通路の端をかすめただけで
 * 当たったことになり、避けたはずなのに死ぬ。
 */
export const BLAST_HITBOX = 0.14;

/* ------------------------------------------------------------------ 試合 */

/** 1ラウンドの制限時間の既定値（秒）。 */
export const ROUND_SECONDS = 180;

/** 勝利数の既定値。 */
export const WINS_TO_TAKE_MATCH = 3;
