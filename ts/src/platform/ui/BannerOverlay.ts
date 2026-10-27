import { SETUP_BUTTON, type BannerView } from '../../presentation/hud/RoundBanner.js';
import { el, pointerButton } from './dom.js';

/** 幕のボタンを押したときに呼ぶもの。 */
export interface BannerHandlers {
  /** 1つ目のボタン（「つぎのラウンド ▶」「もういっかい」。原型の `advanceBanner`）。 */
  readonly advance: () => void;
  /** 「⚙ 設定をやりなおす」（原型の `backToSetup`）。 */
  readonly setup: () => void;
}

/** 幕に並べるボタン。何を押せるかは、1台か通信対戦か・ホストかで違う（`app/Shell.ts`）。 */
export interface BannerButtons {
  /** 1つ目のボタン（文は `BannerView.button`）を出すか。 */
  readonly advance: boolean;
  /** 「⚙ 設定をやりなおす」を出すか。 */
  readonly setup: boolean;
}

/** ボタンを並べない（通信対戦のラウンドの幕）。 */
export const NO_BUTTONS: BannerButtons = { advance: false, setup: false };

/** 勝ち数の行に、原型が直に付けた見た目（L4488・L4496・L4505）。 */
const BOARD_STYLE = 'font-size:16px;letter-spacing:.06em';

/**
 * ラウンドの幕と優勝の幕（原型の `#banner`。L544-550）。中身は `presentation/hud/RoundBanner.ts` が決める。
 *
 * 要素の並びとクラス名は原型と同じにして、原型の CSS をそのまま当てる（`style.css`）。幕は窓の全体を覆う
 * （`#app` の外の `position:fixed`）ので、幕が出ている間は横の板のボタンもつまみも押せない（原型と同じ）。
 *
 * - カード（`.bcard`）の中に、絵文字（`.be`）・題（`.bt`）・文（`.bs`）・ボタンを縦に並べる
 * - 文は原型と同じく1つの要素に、題の下の行・改行・勝ち数の行（16px）・延長戦の行を入れる（原型は `innerHTML` に
 *   `<br>` をつないで書く。この版は要素を1つずつ足す）
 * - ボタンは縦に2つ（原型の `button.go#bAgain` と `button.tbtn.bback#bSetup`）。メニューのカーソルでは1つずつ別の
 *   グループ（`b0`・`b1`）にする（原型の `roundEnd: ['b0','b1']`）。どちらも画面の操作の音を鳴らさない（原型と同じ）
 * - 幕が出るたびに、カードに新しい画面の名前（`data-screen`）を付けるので、メニューのカーソルは1つ目のボタンへ
 *   戻る（原型の `endGame` の `MENU.reset`）。同じ幕でボタンだけが替わったとき（通信対戦で「もういっかい」を消した
 *   とき）は替えない
 */
export class BannerOverlay {
  readonly #root: HTMLElement;
  readonly #handlers: BannerHandlers;
  #shown: BannerView | null = null;
  #buttons: BannerButtons = NO_BUTTONS;
  /** 出した幕の数。幕が出るたびに画面の名前を替える。 */
  #count = 0;

  constructor(root: HTMLElement, handlers: BannerHandlers) {
    this.#root = root;
    this.#handlers = handlers;
    this.#root.hidden = true;
  }

  /**
   * 幕を出す。null なら隠す。同じ幕と同じボタンなら、要素に触れない。
   *
   * @param buttons 並べるボタン
   */
  show(view: BannerView | null, buttons: BannerButtons = NO_BUTTONS): void {
    if (view === this.#shown && buttons.advance === this.#buttons.advance && buttons.setup === this.#buttons.setup) return;
    if (view !== this.#shown && view !== null) this.#count += 1;
    this.#shown = view;
    this.#buttons = buttons;
    if (view === null) {
      this.#root.hidden = true;
      this.#root.replaceChildren();
      return;
    }
    const lines: Node[] = [
      document.createTextNode(view.summary),
      el('br'),
      el('span', { text: view.board, style: BOARD_STYLE }),
      ...(view.note === null ? [] : [el('br'), document.createTextNode(view.note)]),
    ];
    this.#root.hidden = false;
    this.#root.replaceChildren(
      el('div', { className: 'bcard', data: { screen: `banner-${this.#count}` } }, [
        el('div', { className: 'be', text: view.emoji }),
        el('div', { className: 'bt', text: view.title }),
        el('div', { className: 'bs' }, lines),
        buttons.advance
          ? pointerButton(view.button, () => this.#handlers.advance(), { className: 'go', data: { action: 'advance', nav: 'b0' } })
          : null,
        // 原型の HTML は2つのボタンの間に改行と字下げがあり（L548-549）、空白1つとして並ぶ。ボタンは inline-block
        // なので、カードの幅（2つを1行に並べたときの幅）がその空白の分だけ広がる。無いと、ボタンがカードの幅を決める
        // 幕（題が短い幕）でカードが原型より 5px ほど狭い。縦の並びは変わらない（.go は幅 100% なので行の末尾で消える）。
        buttons.advance && buttons.setup ? document.createTextNode(' ') : null,
        buttons.setup
          ? pointerButton(SETUP_BUTTON, () => this.#handlers.setup(), { className: 'tbtn bback', data: { action: 'setup', nav: 'b1' } })
          : null,
      ]),
    );
  }
}
