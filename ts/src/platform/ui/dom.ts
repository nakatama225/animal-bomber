/**
 * 画面の部品を組み立てる小さな関数。
 *
 * 画面の中身（文と値）は `presentation/` の純粋な関数が決め、ここではそれを要素に写すだけにする。
 * 写す側を薄く保つと、ブラウザ無しで確認できない部分が小さくなる。
 *
 * ⚠️ 文は `textContent` で入れる。`innerHTML` に文字列をつなげて入れると、名前などに
 * `<` が入ったときに要素として解釈される。
 */

/** 要素に付けるもの。 */
export interface ElementOptions {
  /** クラス名。空白で区切って複数。 */
  readonly className?: string;
  readonly text?: string;
  /** `data-*` 属性。テストで要素を探す目印にも使う。 */
  readonly data?: Readonly<Record<string, string>>;
  readonly hidden?: boolean;
  /** 要素に直に付ける見た目（`style` 属性の中身）。原型が要素に直に書いた値を写すときだけ使う。 */
  readonly style?: string;
}

/** 要素を1つ作る。 */
export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  options: ElementOptions = {},
  children: readonly (Node | null)[] = [],
): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);
  if (options.className !== undefined) element.className = options.className;
  if (options.text !== undefined) element.textContent = options.text;
  if (options.hidden !== undefined) element.hidden = options.hidden;
  if (options.style !== undefined) element.style.cssText = options.style;
  for (const [key, value] of Object.entries(options.data ?? {})) element.dataset[key] = value;
  for (const child of children) if (child !== null) element.append(child);
  return element;
}

/**
 * ページの先頭へ戻す（原型の `showScreen` の `window.scrollTo(0,0)`。L5697）。試合の前の画面を替えたときと、
 * 試合を始めたときに呼ぶ。
 *
 * 窓は、渡した要素の文書から読む（ファイルの一番外側で `window` に触れない）。`scrollTo` の無い環境では何もしない。
 */
export function scrollToTop(element: Element): void {
  const view = element.ownerDocument.defaultView;
  if (typeof view?.scrollTo === 'function') view.scrollTo(0, 0);
}

/** `pointerButton` で作ったボタンと、押されたときに呼ぶもの。メニューのカーソルで決めたときも同じものを呼ぶ。 */
const HANDLERS = new WeakMap<HTMLElement, () => void>();

/**
 * マウスやタッチで押されたときだけ `handler` を呼ぶボタンを作る。
 *
 * ⚠️ キーボード（Enter・Space）で起きたクリックは捨てる。マウスで押したボタンには
 * フォーカスが残ることがあり、そのあと試合中に Space や Enter（どちらも爆弾のキー）を
 * 押すと、ブラウザがそのボタンをもう一度押す（ポーズ・もういっかい、など）。
 * キーボードで起きたクリックは `detail` が 0 になる。Tab でフォーカスさせないのも
 * 同じ理由（`tabIndex = -1`）。キーボードでメニューを動かすときは、ブラウザのクリックを通さず、
 * カーソルが `activate` で同じ `handler` を呼ぶ。
 */
export function pointerButton(label: string, handler: () => void, options: ElementOptions = {}): HTMLButtonElement {
  const button = el('button', { ...options, text: label });
  button.type = 'button';
  button.tabIndex = -1;
  button.addEventListener('click', (event: MouseEvent) => {
    if (event.detail === 0) return;
    handler();
  });
  HANDLERS.set(button, handler);
  return button;
}

/**
 * `pointerButton` の `handler` を呼ぶ。メニューのカーソルで決めたときに使う。
 *
 * ⚠️ クリックを偽って発生させない（`detail: 1` のクリックを発生させれば同じことが起きるが、
 * キーボードで起きたクリックを捨てる仕組みを、わざとすり抜ける形になる）。
 *
 * @returns 呼べたか。`pointerButton` で作った要素でなければ false
 */
export function activate(element: HTMLElement): boolean {
  const handler = HANDLERS.get(element);
  if (handler === undefined) return false;
  handler();
  return true;
}

/**
 * 選択肢のチップを横に並べた箱（原型の `.chips`）。選ばれているものに印（`on`）を付ける。
 *
 * @param id 箱の目印（`data-field`。テストで行を探すのに使う）と、メニューのカーソルのグループの名前
 * @param choose 選ばれたときに呼ぶ。画面の写し直しも、呼ぶ側がここで行う
 * @param style 箱に直に付ける見た目（原型がチップの箱に直に書いた下の空きなど）
 */
export function chipBox<T>(
  id: string,
  choices: readonly T[],
  current: T,
  text: (value: T) => string,
  choose: (value: T) => void,
  style?: string,
): HTMLElement {
  return el(
    'div',
    { className: 'chips', data: { field: id }, ...(style === undefined ? {} : { style }) },
    choices.map((value) =>
      pointerButton(text(value), () => choose(value), {
        className: `chip${value === current ? ' on' : ''}`,
        // 1行を、メニューのカーソルの1グループにする（左右で選ぶ）。
        data: { value: String(value), nav: id },
      }),
    ),
  );
}

/**
 * 見出しとチップの箱を、1つの行（原型の `.row`）に入れる。
 *
 * 見出しは原型と同じ `label.lb`。原型の CSS は `label` の要素にだけ当たるので、`span.lb`（ルールの画面の
 * CPU の行の札）とは見た目が違う。
 */
export function chipRow<T>(
  label: string,
  id: string,
  choices: readonly T[],
  current: T,
  text: (value: T) => string,
  choose: (value: T) => void,
): HTMLElement {
  return el('div', { className: 'row' }, [
    el('label', { className: 'lb', text: label }),
    chipBox(id, choices, current, text, choose),
  ]);
}
