/**
 * プレイヤーの入力（1 tick ぶんの、押しているボタンの組）。
 *
 * キーボードを押しているか、CPU がそう判断したか、通信で届いたかを
 * **区別しない**。ゲーム本体は、この形になったものだけを受け取る。CPU の
 * 「押す」は、そう決めたという意味で、人間の押したボタンと同じ形で返す。
 *
 * 原型では、人間の操作も CPU の判断も、プレイヤーの座標や爆弾の配列を
 * 直接書き換えていた。そのため「操作を保存して再生する」「操作だけを
 * 送って対戦する」のどちらも、あとから足す場所がなかった。
 *
 * この1つの型があることで、次の3つが同じ仕組みで成り立つ。
 *
 * - リプレイ … 記録した入力を順に流す
 * - 通信対戦 … 相手の入力を受け取って流す
 * - バランス検証 … CPU が返す入力だけで画面なしに大量の試合を回す
 *
 * 将来 CPU を機械学習や強化学習に差し替える場合も、繋ぎ先はここ1点になる。
 */

/** 1 tick ぶんの入力。 */
export interface PlayerInput {
  readonly up: boolean;
  readonly down: boolean;
  readonly left: boolean;
  readonly right: boolean;
  /** 爆弾のボタンを押しているか。 */
  readonly bomb: boolean;
  /** 技のボタンを押しているか。押した長さで通常技ととくぎが分かれる。 */
  readonly action: boolean;
  /**
   * とくぎを直に出すボタンを押しているか。押した瞬間に、通常技を挟まずにとくぎが出る。
   *
   * ⚠️ 人間の操作には割り当てていない。原型の人間は、技のボタンの長押しでしかとくぎを出せない
   * （押した瞬間に通常技も出る）。一方、原型の CPU はボタンを通らずにとくぎを呼んでいた
   * （useSpecial を直に呼ぶ。長押しの待ちも通常技も無い）。この版の CPU は入力しか返せないので、
   * 原型の CPU と同じ出し方をこのボタンで表す。
   */
  readonly special: boolean;
}

/** 何も押していない入力。 */
export const IDLE_INPUT: PlayerInput = Object.freeze({
  up: false,
  down: false,
  left: false,
  right: false,
  bomb: false,
  action: false,
  special: false,
});

/**
 * 入力を 1 バイトに詰める。
 *
 * 通信対戦では、盤面もプレイヤーの座標も送らない。送るのは
 * 「誰が」「どの tick に」「何を押したか」だけで、入力そのものは1人あたり 1 バイトに収まる
 * （実際には JSON の文字列で送るので、1通50バイトほどになる）。
 *
 * ⚠️ ビットの並びは、送る側と受け取る側で同じでなければならない。
 * 送受信の両方がこの関数の対を使う。
 */
export function packInput(playerInput: PlayerInput): number {
  return (
    (playerInput.up ? 1 : 0) |
    (playerInput.down ? 2 : 0) |
    (playerInput.left ? 4 : 0) |
    (playerInput.right ? 8 : 0) |
    (playerInput.bomb ? 16 : 0) |
    (playerInput.action ? 32 : 0) |
    (playerInput.special ? 64 : 0)
  );
}

/**
 * 入力のビットの上限（7つのボタンを全部押した値）。通信の約束と記録の文字列が、読んだ値を確かめるのに使う。
 *
 * 数を直接書かず `packInput` から作る。ボタンを足すと、ここでそのボタンが足りずに型が合わなくなるので、
 * 上限の直し忘れに気づける。
 */
export const MAX_INPUT_BITS = packInput({
  up: true,
  down: true,
  left: true,
  right: true,
  bomb: true,
  action: true,
  special: true,
});

/** 1 バイトから入力を戻す。 */
export function unpackInput(bits: number): PlayerInput {
  return {
    up: (bits & 1) !== 0,
    down: (bits & 2) !== 0,
    left: (bits & 4) !== 0,
    right: (bits & 8) !== 0,
    bomb: (bits & 16) !== 0,
    action: (bits & 32) !== 0,
    special: (bits & 64) !== 0,
  };
}

/** 2つの入力が同じか。連続する同じ入力をまとめるときに使う。 */
export function sameInput(a: PlayerInput, b: PlayerInput): boolean {
  return packInput(a) === packInput(b);
}
