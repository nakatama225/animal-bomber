import type { NoticeSink } from '../../presentation/Presenter.js';
import { el } from './dom.js';

/** 通知を出しておく長さ（ミリ秒）。 */
const SHOW_MS = 2400;

/** 同時に出しておく通知の上限。多すぎると盤面が隠れる。古いものから消す。 */
const MAX_SHOWN = 4;

/**
 * 盤面の上に短く出す通知。
 *
 * 通知の文は `Presenter` が決める。ここは出して、時間がたったら消すだけ。
 */
export class Toasts implements NoticeSink {
  readonly #root: HTMLElement;

  constructor(root: HTMLElement) {
    this.#root = root;
  }

  show(message: string): void {
    const toast = el('div', { className: 'toast', text: message });
    this.#root.append(toast);
    while (this.#root.childElementCount > MAX_SHOWN) this.#root.firstElementChild?.remove();
    setTimeout(() => toast.remove(), SHOW_MS);
  }

  /** 出ている通知を全部消す。試合を抜けるときに使う。 */
  clear(): void {
    this.#root.replaceChildren();
  }
}
