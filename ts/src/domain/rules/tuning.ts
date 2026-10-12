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

/**
 * 2人の試合の開始位置の並び（`SPAWN_CELLS` の番号）。左上と右下の対角（原型と同じ）。
 *
 * 上の2隅だと、2人が同じ辺に並ぶ（横に20マス）。対角なら縦横あわせて34マス離れる。
 * 盤面を広げたのと同じ理由で、開始直後に相手と出会わないようにする。
 * 1台で2人＋CPU2体のときも、2人はこの対角から始まる（`localSetup.ts` の `LOCAL_SPAWN_ORDER`）。
 * ⚠️ 延長戦で移る隅は、この並びによらず、加わる人にプレイヤー番号の順で `SPAWN_CELLS` の隅を割り当てる
 * （原型と同じ）。2人の試合でも、2P は延長戦で右下から右上へ移る。
 */
export const DUEL_SPAWN_ORDER: readonly number[] = [0, 3];

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
 * 速度の下限（1秒あたりのマス数）。原型の値で、理由の記録は無い。
 *
 * 効くのは、ブロックの中を進んでいる間に「超スロー」がかかったときだけ（ほかは、いちばん
 * 遅い組み合わせでもこれより速い）。下限には「超スロー」の倍率を掛けない（原型の getSpeed は
 * 最後にこの値と上限で挟む）。
 */
export const MIN_SPEED_PER_SECOND = 0.42;
export const MIN_SPEED = MIN_SPEED_PER_SECOND / TICKS_PER_SECOND;

/**
 * 壊せるブロックの中を進んでいる間の速さの倍率（原型の DIG_PENALTY）。足の速さと靴の
 * ぶんの合計に掛ける。
 *
 * ブロックを抜けられる能力が強すぎないように、とても遅くしてある。靴のぶんにも同じ倍率を
 * 掛けるだけで、靴だけをさらに弱める扱いはしない（原型の作者は一度 10% まで弱めすぎて
 * 「弱すぎる」と戻した。2026-08-09）。ブロックの中では「とまれない」の下限は効かず、
 * 「超スロー」は効く（原型の getSpeed）。
 */
export const IN_BLOCK_SPEED_RATIO = 0.18;

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

/* ------------------------------------------------------------------ 体力 */

/**
 * 爆風1回あたりに減る体力（半分の単位）。
 *
 * 体力を半分の単位で持つのは、技の最中に爆風を受けても半分だけ減る動物がいるため。
 * 画面の「爆風 N 回で倒れる」は、体力をこの値で割って切り上げて出す（体力3なら2回で倒れる）。
 */
export const BLAST_DAMAGE = 2;

/**
 * 体力の既定値（半分の単位）。爆風1回で倒れる（原型の既定 hpP1・hpP2・hpCPU = 1 と同じ）。
 *
 * 設定の画面で1人ずつ変えられる（ハンデをつけるため）。
 * 動物ごとの上乗せは、この値に足す。
 */
export const STARTING_HP = 2;

/* --------------------------------------------------------- 一時的な状態 */

/** 「超スロー」がかかっているときの速度の倍率。 */
export const SLOW_FACTOR = 0.42;

/**
 * 「とまれない」がかかっているときの速度の下限（上限速度に対する割合）。
 *
 * ⚠️ 下限そのものにも「超スロー」の倍率をかける。単純に下限を敷くと、
 * 超スローを踏んだあとに「とまれない」を踏んだ人が**速くなる**
 * という逆転が起きる。後から踏んだ悪い状態が前のものを打ち消してしまう。
 *
 * 重ねがけを認めてから起こりうるようになった。上書きだった頃は
 * 2つが同時にかかること自体が無かったので表に出なかった。
 */
export const RUNAWAY_SPEED_FLOOR_RATIO = 0.92;

/** バナナで滑っているときの速度の倍率。 */
export const SLIDE_SPEED_RATIO = 1.25;

/** 「爆風1マス」がかかっているときの火力。 */
export const WEAKENED_POWER = 1;

/**
 * 「勝手に設置」が爆弾を置こうとする間隔（秒）。置けなかった拍も、次は1拍あと。
 *
 * ⚠️ 毎 tick 置こうとしない。毎 tick だと、歩きながら隣り合うマスに続けて置き、
 * 爆発で手持ちが戻った次の tick に置き直す。原型は 0.5 秒に1回で、素の速さで
 * 歩くと1マスおきに並ぶ。
 */
export const AUTOBOMB_INTERVAL_SECONDS = 0.5;
export const AUTOBOMB_INTERVAL: Tick = secondsToTicks(AUTOBOMB_INTERVAL_SECONDS);
