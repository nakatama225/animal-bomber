/**
 * メニューをキーボードやゲームパッドで動かすときの操作。
 *
 * キーボードの矢印・Enter と、パッドの十字・A は、どちらもこの操作に翻訳してから渡す。
 * 操作の意味を決める場所を1つにするため（原型も同じ形）。
 */
export type NavCommand = 'up' | 'down' | 'left' | 'right' | 'confirm' | 'back';

/** 操作を受けた結果。 */
export type NavResult =
  /** 何もしない（並びが空・枠を出しただけ、など）。 */
  | { readonly kind: 'none' }
  /** カーソルが動いた、または枠を出した。描き直す。 */
  | { readonly kind: 'moved' }
  /** この項目を押す。 */
  | { readonly kind: 'activate'; readonly group: number; readonly item: number }
  /** 1つ前の画面へ戻る。 */
  | { readonly kind: 'back' };

/**
 * 枠が出ていないときの決定をどう扱うか。
 *
 * - `show`：枠を出すだけで、押さない（ふつうの画面）
 * - `activate`：枠を出し、そのまま押す（試合が決まった幕）
 */
export type HiddenConfirm = 'show' | 'activate';

const NONE: NavResult = { kind: 'none' };
const MOVED: NavResult = { kind: 'moved' };

/**
 * メニューのカーソル。**どの項目を指しているかだけを持ち、画面には触れない。**
 *
 * 項目は「グループ」の並びで、グループの中に項目が並ぶ（2段）。上下でグループを移り、
 * 左右でグループの中を移る。端まで行くと反対の端へ回る。
 *
 * - 縦に並ぶボタン（タイトルの遊び方の一覧）は、1つずつ別のグループにする
 * - 横に並ぶもの（動物の一覧・選択肢の1行）だけが、1つのグループに複数入る
 *
 * ⚠️ 画面上の座標では動かさない。動物の一覧は画面の幅で列の数が変わるので、
 * 「1つ下」がどれかはコードから決まらない（原型の注意書き）。
 *
 * ## 枠は、キーやパッドを触るまで出さない
 *
 * マウスで遊ぶ人には枠は要らない。枠が出ていないときの最初の1押しは、まず枠を出す。
 * ⚠️ そのとき飲み込むのは決定だけ。移動と戻るまで飲み込むと、マウスに触れたあとの
 * 最初の1押しが毎回効かず、「たまに効かない」に見える。危ないのは、どこを指しているか
 * 見えないまま決定することだけ（原型の注意書き）。
 *
 * ⚠️ 試合が決まった幕だけは、最初の決定をそのまま効かせる（`HiddenConfirm` の `activate`）。
 * 幕でする操作はほぼ「もういっかい」だけで、カーソルも幕が出るたびに「もういっかい」へ戻す。
 * 1回目を飲み込むと「決定が効かない」としか見えない。原型もキーボードの Space・Enter は
 * そのまま次へ進め、パッドの A も1回目を飲み込まなかった。
 */
export class MenuCursor {
  #group = 0;
  #item = 0;
  #shown = false;

  /** 枠を出しているか。 */
  get shown(): boolean {
    return this.#shown;
  }

  get group(): number {
    return this.#group;
  }

  get item(): number {
    return this.#item;
  }

  /** 先頭へ戻す。画面が替わったときに呼ぶ。枠の出し方は変えない。 */
  reset(): void {
    this.#group = 0;
    this.#item = 0;
  }

  /** 枠を消す。マウスを動かしたときに呼ぶ。 */
  hide(): void {
    this.#shown = false;
  }

  /**
   * 操作を1つ受ける。
   *
   * @param sizes いまの画面の、グループごとの項目の数（上から順）。空のグループは含めない
   * @param hiddenConfirm 枠が出ていないときの決定をどう扱うか
   */
  handle(command: NavCommand, sizes: readonly number[], hiddenConfirm: HiddenConfirm = 'show'): NavResult {
    if (sizes.length === 0) return NONE;
    this.fit(sizes);
    if (!this.#shown) {
      this.#shown = true;
      if (command === 'confirm' && hiddenConfirm === 'show') return MOVED;
    }
    switch (command) {
      case 'back':
        return { kind: 'back' };
      case 'confirm':
        return { kind: 'activate', group: this.#group, item: this.#item };
      case 'up':
      case 'down': {
        const step = command === 'down' ? 1 : -1;
        this.#group = (this.#group + step + sizes.length) % sizes.length;
        // 項目の少ないグループへ移ると、項目の番号がはみ出すことがある。
        this.fit(sizes);
        return MOVED;
      }
      case 'left':
      case 'right': {
        const size = sizes[this.#group] ?? 1;
        const step = command === 'right' ? 1 : -1;
        this.#item = (this.#item + step + size) % size;
        return MOVED;
      }
    }
  }

  /**
   * 並びの外を指していたら、中へ丸める。
   *
   * 項目が減ったとき（選んだものによって行が消える、など）に要る。
   */
  fit(sizes: readonly number[]): void {
    if (sizes.length === 0) return;
    this.#group = Math.min(Math.max(this.#group, 0), sizes.length - 1);
    const size = sizes[this.#group] ?? 1;
    this.#item = Math.min(Math.max(this.#item, 0), size - 1);
  }
}
