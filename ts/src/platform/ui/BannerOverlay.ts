import type { BannerView } from '../../presentation/hud/RoundBanner.js';
import { el } from './dom.js';

/**
 * 盤面に重ねる幕。中身は `presentation/hud/RoundBanner.ts` が決める。
 *
 * 試合が決まった幕には、下にボタンを並べられる（もう一度・タイトルへ）。
 * ボタンは呼び出し側が作って渡す。何を押せるかは、1台か通信対戦かで違う。
 */
export class BannerOverlay {
  readonly #root: HTMLElement;
  #shown: BannerView | null = null;
  #actions: readonly HTMLElement[] = [];

  constructor(root: HTMLElement) {
    this.#root = root;
    this.#root.hidden = true;
  }

  /**
   * 幕を出す。null なら隠す。
   *
   * @param actions 試合が決まった幕の下に並べるもの
   */
  show(view: BannerView | null, actions: readonly HTMLElement[] = []): void {
    if (view === this.#shown && sameItems(actions, this.#actions)) return;
    this.#shown = view;
    this.#actions = actions;
    if (view === null) {
      this.#root.hidden = true;
      this.#root.replaceChildren();
      return;
    }
    this.#root.hidden = false;
    this.#root.replaceChildren(
      el('div', { className: 'banner-emoji', text: view.emoji }),
      el('div', { className: 'banner-title', text: view.title }),
      ...view.lines.map((line) => el('div', { className: 'banner-line', text: line })),
      // 試合が決まった幕のボタンの並びは、メニューのカーソルから見て1つの画面にする（`data-screen`）。
      // ラウンドの間の幕（ボタンが無い）から替わったところで、カーソルが先頭（もういっかい）へ戻る。
      // 原型も、試合が決まるたびにカーソルを先頭へ戻していた。
      ...(view.final && actions.length > 0
        ? [el('div', { className: 'banner-actions', data: { screen: 'final' } }, actions)]
        : []),
    );
  }
}

function sameItems<T>(a: readonly T[], b: readonly T[]): boolean {
  return a.length === b.length && a.every((item, index) => item === b[index]);
}
