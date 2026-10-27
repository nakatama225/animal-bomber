import { DIALOG_NO, DIALOG_TEXTS, type DialogKind } from '../../presentation/menu/menuText.js';
import { activate, el, pointerButton } from './dom.js';

/**
 * 確認の画面（原型の `askConfirm`。L3352-3375）。窓の全体を暗くして、真ん中に文と2つのボタンを出す。
 *
 * ⛔ ブラウザの `confirm()` を使わない（原型の注記）。OS の確認はパッドで操作できないので、パッドだけで遊んで
 * いても、最後の1枚だけはトラックパッドで押さなければならなくなる。画面の中に出し、カーソルが乗る2つのボタンにする。
 *
 * - 左は「やめる」、右は種類ごとの文（「設定へもどる」など）。カーソルは初めに「やめる」を指す（危ない側を
 *   初めの位置にしない。原型の注記）。開くと、カーソルで動かす画面がこの要素に替わるので、メニューのカーソル
 *   （`MenuNavigator`）が先頭へ戻す
 * - どちらのボタンも、画面の操作の音を鳴らしてから閉じる（原型 L3369-3370）。右は、閉じてから `onYes` を呼ぶ
 * - 閉じると、カーソルは下の画面の先頭へ戻る（原型の `MENU.closeDialog` の `MENU.reset`。画面の名前が替わるので、
 *   `MenuNavigator` が戻す）
 *
 * 要素は `#app` の外に1つだけ置く（`index.html`）。盤面の上にもメニューの上にも出すため。
 * 開いている間のキーとパッドを確認の画面へ回すのと、P と幕送りを止めるのは `app/Shell.ts`。
 */
export class ConfirmDialog {
  readonly #root: HTMLElement;
  readonly #uiSound: () => void;
  /** 開いているときの「やめる」。閉じていれば null。 */
  #no: HTMLElement | null = null;

  /**
   * @param root 確認の画面を出す要素（`index.html` の `#cfmWrap`）
   * @param uiSound 画面の操作の音を鳴らす（音の解錠も、呼ぶ側がここで行う）
   */
  constructor(root: HTMLElement, uiSound: () => void) {
    this.#root = root;
    this.#uiSound = uiSound;
    this.#root.hidden = true;
  }

  /** 開いているか。 */
  get open(): boolean {
    return this.#no !== null;
  }

  /** 開いている間、カーソルで動かす要素。 */
  get root(): HTMLElement {
    return this.#root;
  }

  /**
   * 開く（原型の `askConfirm`）。閉じているときに呼ぶ（開いている間のパッドとキーは確認の画面へ回るので、`Shell` は
   * 開いている間に開き直さない）。
   *
   * @param onYes 右のボタンを押したときに呼ぶ（閉じたあと）
   */
  ask(kind: DialogKind, onYes: () => void): void {
    const { message, yes } = DIALOG_TEXTS[kind];
    const answer =
      (agreed: boolean): (() => void) =>
      () => {
        this.#uiSound();
        this.close();
        if (agreed) onYes();
      };
    const no = pointerButton(DIALOG_NO, answer(false), { className: 'chip', data: { action: 'no', nav: 'dialog' } });
    this.#root.replaceChildren(
      el('div', { className: 'cfmBox' }, [
        el('div', { className: 'cfmMsg', text: message }),
        el('div', { className: 'cfmBtns' }, [
          no,
          pointerButton(yes, answer(true), { className: 'chip', data: { action: 'yes', nav: 'dialog' } }),
        ]),
      ]),
    );
    this.#no = no;
    this.#root.hidden = false;
  }

  /** 「やめる」を押したのと同じことをする（B・Escape。原型の `MENU.back` は「やめる」の中身を呼ぶ。音も鳴る）。 */
  cancel(): void {
    if (this.#no !== null) activate(this.#no);
  }

  /**
   * 音を鳴らさずに畳む。画面が替わったとき（原型の `showScreen` の `MENU.closeDialog`）・盤面を出したとき・
   * 試合からタイトルへ戻ったときに呼ぶ。開いていなければ何もしない。
   */
  close(): void {
    if (this.#no === null) return;
    this.#no = null;
    this.#root.hidden = true;
    this.#root.replaceChildren();
  }
}
