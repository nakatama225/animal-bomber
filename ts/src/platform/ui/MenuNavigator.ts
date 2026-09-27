import { MenuCursor, type NavCommand, type NavResult } from '../../presentation/menu/MenuCursor.js';
import { activate } from './dom.js';

/** カーソルが指している項目に付ける印。 */
const CURSOR_CLASS = 'navcur';

/**
 * メニューのカーソルを、いま出ている画面の要素に写す。
 *
 * どの項目を指しているかは `MenuCursor`（純粋）が持つ。ここは、画面から項目の並びを取り出し、
 * 決めた項目の `pointerButton` の中身を呼び、印を付け直す。
 *
 * ## 項目の並びは、操作のたびに画面から取り直す
 *
 * 画面は選ぶたびに丸ごと組み直す（`MenuView.render`）ので、要素を覚えておくと古くなる。
 * 項目には、組み立てる側が `data-nav`（グループの名前）を付けておく。ここでは
 * `data-nav` の付いた要素を画面の並びの順に集め、同じ名前ごとに1グループにする。
 * 「← もどる」には付けない（戻るは Escape・B。カーソルに載せると同じ操作が2通りになる）。
 *
 * 画面が替わったら（`data-screen` が変わったら）カーソルを先頭へ戻す。
 * 同じ画面の中で選び直しただけなら、カーソルはそのまま。
 */
export class MenuNavigator {
  readonly #cursor = new MenuCursor();
  /** 最後に見た画面の名前。 */
  #screen: string | null = null;

  /** 枠を出しているか。 */
  get shown(): boolean {
    return this.#cursor.shown;
  }

  /**
   * 操作を1つ受ける。決定なら、その項目を押す。
   *
   * @param root いま操作できる画面の要素（メニュー・ラウンドの間の幕）
   * @returns 何をしたか。`back` のときに戻るのは呼ぶ側の役目（どこへ戻るかは画面ごとに違う）
   */
  handle(root: HTMLElement, command: NavCommand): NavResult {
    this.#noticeScreen(root);
    const groups = groupsIn(root);
    const result = this.#cursor.handle(command, groups.map((group) => group.length));
    if (result.kind === 'activate') {
      const target = groups[result.group]?.[result.item];
      if (target !== undefined) activate(target);
    }
    this.paint(root);
    if (result.kind === 'moved') this.#current(root)?.scrollIntoView?.({ block: 'nearest' });
    return result;
  }

  /** 枠を消す。マウスを動かしたときに呼ぶ。 */
  hide(root: HTMLElement): void {
    if (!this.#cursor.shown) return;
    this.#cursor.hide();
    this.paint(root);
  }

  /**
   * 印を付け直す。画面が組み直されたあとに呼ぶ（何度呼んでもよい）。
   *
   * ⚠️ 画面が替わっていたら、ここでもカーソルを先頭へ戻す。決定した項目が画面を替えたとき、
   * 次の操作を待たずに新しい画面の先頭に印が付く。
   */
  paint(root: HTMLElement): void {
    this.#noticeScreen(root);
    for (const element of root.querySelectorAll<HTMLElement>(`.${CURSOR_CLASS}`)) {
      element.classList.remove(CURSOR_CLASS);
    }
    if (this.#cursor.shown) this.#current(root)?.classList.add(CURSOR_CLASS);
  }

  #current(root: HTMLElement): HTMLElement | undefined {
    const groups = groupsIn(root);
    const sizes = groups.map((group) => group.length);
    if (sizes.length === 0) return undefined;
    this.#cursor.fit(sizes);
    return groups[this.#cursor.group]?.[this.#cursor.item];
  }

  #noticeScreen(root: HTMLElement): void {
    const screen = screenOf(root);
    if (screen === this.#screen) return;
    this.#screen = screen;
    this.#cursor.reset();
  }
}

/** その画面の名前。メニューは `data-screen`、それ以外は要素の id。 */
function screenOf(root: HTMLElement): string {
  const named = root.querySelector<HTMLElement>('[data-screen]');
  return named?.dataset['screen'] ?? root.id;
}

/** 画面の中の項目を、グループごとに並べる（画面の並びの順）。 */
function groupsIn(root: HTMLElement): HTMLElement[][] {
  const groups = new Map<string, HTMLElement[]>();
  for (const element of root.querySelectorAll<HTMLElement>('[data-nav]')) {
    const name = element.dataset['nav'] ?? '';
    const group = groups.get(name);
    if (group === undefined) groups.set(name, [element]);
    else group.push(element);
  }
  return [...groups.values()];
}
