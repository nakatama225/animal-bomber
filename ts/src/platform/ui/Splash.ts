import { VERSION_LINE } from '../../presentation/menu/manual.js';
import { LOGO, SPLASH_PROMPT, SUBTITLE } from '../../presentation/menu/menuText.js';
import { el } from './dom.js';

/** 何もしなくても消え始めるまで（原型の `setTimeout(dismiss, 3200)`。L5760）。 */
export const SPLASH_AUTO_MS = 3200;

/**
 * 消え始めてから、要素を隠すまで（原型の `setTimeout(…display='none', 500)`。L5757）。
 *
 * 薄れる長さ（0.45 秒）は CSS の `transition` が持つ（`style.css` の `#splash`）。隠すのは薄れ終わったあと。
 */
export const SPLASH_GONE_MS = 500;

/** あとで呼ぶ。起動の入口がブラウザの `setTimeout` を渡す（テストでは差し替える）。 */
export type Schedule = (callback: () => void, ms: number) => void;

/**
 * 起動の幕（原型の `#splash`。L552-559・L5752-5761）。
 *
 * ロゴ・題・版の行と、点滅する案内を全面に出す。クリックか、キーボードのどれかのキーで消え始め、何もしなくても
 * 3.2 秒で消え始める。消え始めたら薄れ（`.off`）、0.5 秒後に隠す。どの合図でも、消し始めるのは1回目だけ
 * （2回目からは何もしない）。
 *
 * - パッドのボタンでは消えない（原型も消す合図を登録していない）。音も鳴らさない（原型と同じ）
 * - 幕を消したキーは、下のタイトルにも届く（原型と同じ。キーの合図は、メニューのキーとは別に登録する）。Enter なら
 *   カーソルの枠が出るだけ、矢印なら枠が出て1つ動く
 *
 * ⚠️ 要素は `index.html` で `#app` の外に置き、`hidden` で隠しておく（全面を覆うので、出さないときは隠したままにする）。
 */
export class Splash {
  readonly #root: HTMLElement;
  readonly #schedule: Schedule;
  #dismissed = false;

  constructor(root: HTMLElement, schedule: Schedule) {
    this.#root = root;
    this.#schedule = schedule;
  }

  /** 消え始めたか。 */
  get dismissed(): boolean {
    return this.#dismissed;
  }

  /**
   * 幕を出し、消える合図を待つ。
   *
   * @param keys キーの合図を受ける所（起動の入口は `window` を渡す）
   */
  show(keys: EventTarget): void {
    this.#root.replaceChildren(
      el('div', { className: 'titleWrap' }, [
        el('div', { className: 'logoPlate' }, [el('span', { className: 'logo', text: LOGO })]),
        el('div', { className: 'logoSub', text: SUBTITLE }),
        el('div', { className: 'ver', text: VERSION_LINE }),
      ]),
      el('div', { className: 'tap', text: SPLASH_PROMPT }),
    );
    this.#root.hidden = false;
    this.#root.addEventListener('click', () => this.dismiss());
    keys.addEventListener('keydown', () => this.dismiss(), { once: true });
    this.#schedule(() => this.dismiss(), SPLASH_AUTO_MS);
  }

  /** 消し始める（1回目だけ）。 */
  dismiss(): void {
    if (this.#dismissed) return;
    this.#dismissed = true;
    this.#root.classList.add('off');
    this.#schedule(() => {
      this.#root.hidden = true;
    }, SPLASH_GONE_MS);
  }
}
