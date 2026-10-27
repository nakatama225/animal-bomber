import { Toast } from '../../presentation/hud/toast.js';
import type { NoticeSink } from '../../presentation/Presenter.js';

/** 時刻を読むものと、あとで呼ぶもの（テストで差し替える）。 */
export interface ToastClock {
  /** いまの時刻（ミリ秒）。 */
  readonly now: () => number;
  /** `ms` ミリ秒たったら `callback` を呼ぶ。 */
  readonly after: (callback: () => void, ms: number) => void;
}

/**
 * 画面の上に出す通知（原型の `#toast` と `toast`。L567・L6088-6096）。
 *
 * 通知は1枚だけ。新しい文が来たら積まずに置き換え、最後に出してから 1.4 秒で薄れ始める（どれが出ているかは
 * `presentation/hud/toast.ts` の `Toast` が持つ）。濃くなる・薄れるのは CSS の `transition:opacity .2s` に任せる
 * （原型と同じ）。ここは文を書き、`on` を付け外しするだけ。
 *
 * 要素は `#app` の外に1つあり、どの画面の上にも出る（原型と同じ）。画面を替えても消さない（原型の
 * `backToSetup` も触らない）ので、タイトルへ戻ったあとも、残りの時間だけ出る。
 */
export class Toasts implements NoticeSink {
  readonly #root: HTMLElement;
  readonly #state = new Toast();
  readonly #clock: ToastClock;
  /** 消すための読み直しを、もう頼んであるか（同時に1つだけ頼む）。 */
  #waiting = false;

  /** @param clock 省くと実時間（`Date.now` と `setTimeout`）。ファイルの一番外側では読まない */
  constructor(root: HTMLElement, clock?: ToastClock) {
    this.#root = root;
    this.#clock = clock ?? { now: () => Date.now(), after: (callback, ms) => setTimeout(callback, ms) };
  }

  show(message: string): void {
    this.#state.show(message, this.#clock.now());
    this.#paint();
  }

  /**
   * いまの通知を写す。出している間は、消え始める時刻にもう一度読み直す。
   *
   * 読み直したときに、そのあいだに新しい通知が来ていれば、まだ出したままなので、その残りの時間でもう一度頼む
   * （原型が `clearTimeout` して数え直すのと同じ）。
   */
  #paint(): void {
    const now = this.#clock.now();
    const view = this.#state.view(now);
    if (view === null) return;
    if (this.#root.textContent !== view.text) this.#root.textContent = view.text;
    this.#root.classList.toggle('on', view.on);
    if (!view.on || this.#waiting) return;
    this.#waiting = true;
    this.#clock.after(() => {
      this.#waiting = false;
      this.#paint();
    }, this.#state.remaining(now));
  }
}
