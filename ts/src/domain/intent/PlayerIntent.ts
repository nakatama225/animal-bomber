/**
 * 1 tick ぶんの「何をしたいか」。
 *
 * キーボードを押しているか、CPU がそう判断したか、通信で届いたかを
 * **区別しない**。ゲーム本体は、この形になったものだけを受け取る。
 *
 * 原型では、人間の操作も CPU の判断も、プレイヤーの座標や爆弾の配列を
 * 直接書き換えていた。そのため「操作を保存して再生する」「操作だけを
 * 送って対戦する」のどちらも、あとから足す場所がなかった。
 *
 * この1つの型があることで、次の3つが同じ仕組みで成り立つ。
 *
 * - リプレイ … 記録した意思を順に流す
 * - 通信対戦 … 相手の意思を受け取って流す
 * - バランス検証 … CPU の意思だけで画面なしに大量の試合を回す
 *
 * 将来 CPU を機械学習や強化学習に差し替える場合も、繋ぎ先はここ1点になる。
 */

/** 1 tick ぶんの操作の意思。 */
export interface PlayerIntent {
  readonly up: boolean;
  readonly down: boolean;
  readonly left: boolean;
  readonly right: boolean;
  /** 爆弾のボタンを押しているか。 */
  readonly bomb: boolean;
  /** 技のボタンを押しているか。押した長さで通常技ととくぎが分かれる。 */
  readonly action: boolean;
}

/** 何もしない意思。 */
export const IDLE_INTENT: PlayerIntent = Object.freeze({
  up: false,
  down: false,
  left: false,
  right: false,
  bomb: false,
  action: false,
});

/**
 * 意思を 1 バイトに詰める。
 *
 * 通信対戦では、盤面もプレイヤーの座標も送らない。送るのは
 * 「誰が」「どの tick に」「何をしたか」だけで、意思そのものは1人あたり 1 バイトに収まる
 * （実際には JSON の文字列で送るので、1通50バイトほどになる）。
 *
 * ⚠️ ビットの並びは、送る側と受け取る側で同じでなければならない。
 * 送受信の両方がこの関数の対を使う。
 */
export function packIntent(intent: PlayerIntent): number {
  return (
    (intent.up ? 1 : 0) |
    (intent.down ? 2 : 0) |
    (intent.left ? 4 : 0) |
    (intent.right ? 8 : 0) |
    (intent.bomb ? 16 : 0) |
    (intent.action ? 32 : 0)
  );
}

/**
 * 意思のビットの上限（6つのボタンを全部押した値）。通信の約束と記録の文字列が、読んだ値を確かめるのに使う。
 *
 * 数を直接書かず `packIntent` から作る。ボタンを足すと、ここでそのボタンが足りずに型が合わなくなるので、
 * 上限の直し忘れに気づける。
 */
export const MAX_INTENT_BITS = packIntent({
  up: true,
  down: true,
  left: true,
  right: true,
  bomb: true,
  action: true,
});

/** 1 バイトから意思を戻す。 */
export function unpackIntent(bits: number): PlayerIntent {
  return {
    up: (bits & 1) !== 0,
    down: (bits & 2) !== 0,
    left: (bits & 4) !== 0,
    right: (bits & 8) !== 0,
    bomb: (bits & 16) !== 0,
    action: (bits & 32) !== 0,
  };
}

/** 2つの意思が同じか。連続する同じ入力をまとめるときに使う。 */
export function sameIntent(a: PlayerIntent, b: PlayerIntent): boolean {
  return packIntent(a) === packIntent(b);
}
