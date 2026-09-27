/**
 * 画面の部品を組み立てる小さな道具。
 *
 * 画面の中身（文と値）は `presentation/` の純粋な関数が決め、ここではそれを要素に写すだけにする。
 * 写す側を薄く保つと、ブラウザ無しで確かめられない部分が小さくなる。
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
  for (const [key, value] of Object.entries(options.data ?? {})) element.dataset[key] = value;
  for (const child of children) if (child !== null) element.append(child);
  return element;
}

/**
 * マウスやタッチで押されたときだけ `handler` を呼ぶボタンを作る。
 *
 * ⚠️ キーボード（Enter・Space）で起きたクリックは捨てる。どちらも爆弾のキーなので、
 * 試合を始めるボタンをキーボードで押すと、押したまま試合が始まって最初の tick で
 * 開始位置に爆弾を置く。キーボードで起きたクリックは `detail` が 0 になる。
 * Tab でフォーカスさせないのも同じ理由（`tabIndex = -1`）。
 */
export function pointerButton(label: string, handler: () => void, options: ElementOptions = {}): HTMLButtonElement {
  const button = el('button', { ...options, text: label });
  button.type = 'button';
  button.tabIndex = -1;
  button.addEventListener('click', (event: MouseEvent) => {
    if (event.detail === 0) return;
    handler();
  });
  return button;
}

/**
 * 選択肢を横に並べた1行。選ばれているものに印（`on`）を付ける。
 *
 * @param id 行の目印（`data-field`）。テストで行を探すのに使う
 * @param choose 選ばれたときに呼ぶ。画面の写し直しも、呼ぶ側がここで行う
 */
export function chipRow<T>(
  label: string,
  id: string,
  choices: readonly T[],
  current: T,
  text: (value: T) => string,
  choose: (value: T) => void,
): HTMLElement {
  return el('div', { className: 'field', data: { field: id } }, [
    el('span', { className: 'field-label', text: label }),
    el(
      'div',
      { className: 'chips' },
      choices.map((value) =>
        pointerButton(text(value), () => choose(value), {
          className: `chip${value === current ? ' on' : ''}`,
          data: { value: String(value) },
        }),
      ),
    ),
  ]);
}
