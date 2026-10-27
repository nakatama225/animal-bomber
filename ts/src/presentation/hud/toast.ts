/**
 * 画面の上に出す通知の状態（原型の `toast` L6088-6096 と `.toast` の CSS L151-155）。
 *
 * 通知は1枚だけ。新しい文が来たら積まずに置き換え、最後に出してから 1400 ms で消え始める。濃くなる・
 * 薄れるのは CSS の `transition:opacity .2s` に任せる（原型と同じ）ので、ここは「出しているか」だけを持つ。
 * 原型は消え始めたあとも要素に文を残す（`on` を外すだけ）ので、ここも文を残す。
 *
 * 時刻は呼ぶ側がミリ秒で渡す。この型は時計を持たない（テストで時刻を決めて渡せる）。試合の盤面の時刻
 * ではなく実時間で数える（原型も `setTimeout` で数え、ポーズの間も消える）。画面を替えても消さない
 * （原型の `backToSetup` も触らない）。
 */

/** 最後に出してから消え始めるまで（原型の `setTimeout(…, 1400)`）。 */
export const TOAST_SHOW_MS = 1400;

/** 濃くなる・薄れるのにかかる長さ（原型の `transition:opacity .2s`）。写す側の CSS がこの長さで変化させる。 */
export const TOAST_FADE_MS = 200;

/** いま写す通知。 */
export interface ToastView {
  readonly text: string;
  /** 出しているか（原型の `.toast.on`）。false なら薄れて消える（文は残す）。 */
  readonly on: boolean;
}

/** 通知1枚の状態。 */
export class Toast {
  #text: string | null = null;
  /** 最後に出した時刻（消え始めるまでの 1400 ms をここから数える）。 */
  #shownAt = 0;

  /** 通知を出す。出ている通知は置き換え、消え始めるまでを数え直す（原型の `clearTimeout`）。 */
  show(text: string, nowMs: number): void {
    this.#text = text;
    this.#shownAt = nowMs;
  }

  /** 時刻 `nowMs` に写す通知。一度も出していなければ null。 */
  view(nowMs: number): ToastView | null {
    if (this.#text === null) return null;
    return { text: this.#text, on: this.remaining(nowMs) > 0 };
  }

  /**
   * 時刻 `nowMs` から消え始めるまでの残り（ミリ秒）。出していないとき・消え始めたあとは 0。
   *
   * 写す側は、この長さのあとにもう一度 `view` を読んで消す。決まった長さで読み直すと、時計の刻みの都合で少し
   * 早く呼ばれたときに、出したまま残る。
   */
  remaining(nowMs: number): number {
    if (this.#text === null) return 0;
    return Math.max(0, TOAST_SHOW_MS - (nowMs - this.#shownAt));
  }
}
