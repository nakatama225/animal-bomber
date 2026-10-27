/**
 * メニューをキーボードやゲームパッドで動かすときの操作。
 *
 * キーボードの矢印・Enter と、パッドの十字・A は、どちらもこの操作に翻訳してから渡す。
 * 操作の意味を決める場所を1つにするため（原型も同じ形）。
 *
 * - `start`：パッドの Start。メニューではカーソルを動かさず、枠を出すだけ
 * - `select`：パッドの Select（Back）。メニューではカーソルを動かさず、枠を出すだけ
 * - `other`：パッドのほかのボタン（X・Y・L1・R1・L2・R2）。カーソルを動かさず、枠を出すだけ。
 *   原型はパッドのどのボタンの押し始めもカーソルへ渡すので、枠が出ていなければどのボタンでも枠が出る
 */
export type NavCommand = 'up' | 'down' | 'left' | 'right' | 'confirm' | 'back' | 'start' | 'select' | 'other';

/** 操作を受けた結果。 */
export type NavResult =
  /** 何もしない（並びが空・関係の無い操作、など）。 */
  | { readonly kind: 'none' }
  /** カーソルが動いた、または枠を出した。描き直す。 */
  | { readonly kind: 'moved' }
  /** この項目を押す。 */
  | { readonly kind: 'activate'; readonly group: number; readonly item: number }
  /** 1つ前の画面へ戻る。 */
  | { readonly kind: 'back' };

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
 * 最初の1押しが毎回反映されず、「たまに反応しない」に見える。危ないのは、どこを指しているか
 * 見えないまま決定することだけ（原型の注意書き）。
 *
 * 幕（ラウンドの幕・優勝の幕）は、このカーソルの決まりの外で扱う（`app/Shell.ts`）。キーボードの Space・Enter は
 * カーソルの位置によらず1つ目のボタンを押し、パッドを試合に繋ぐ遊び方では、幕の間は毎フレームと、パッドの操作を
 * 渡す前に枠を出しておく（`show`）ので、パッドの1回目の A を飲み込まない（原型 L3082-3084・L3632-3637）。
 *
 * ## 1回に届く操作は1つとは限らない
 *
 * パッドは1回の読み取りで、押し始めたボタンをまとめて渡す（原型の `hit`）。原型の `MENU.nav`
 * （L3288-3322）と同じ順に見る：枠が出ていなければ枠を出し、決定が含まれていれば（ふつうの画面では）
 * ほかの操作ごと飲み込む。続けて、戻るがあれば戻るだけ、なければ決定があれば決定だけ、なければ上下を
 * 動かしてから左右を動かす（上下と左右は同じ回に両方動く。下は上より、右は左より先に見る）。
 * キーボードは1回に1つを渡す。
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
   * 操作を待たずに枠を出す。位置は変えない。
   *
   * 原型が `MENU.on = true` を直に書く2か所で使う：パッドを試合に繋ぐ遊び方の幕（毎フレーム。L3637）と、
   * パッドの Select で「設定へもどりますか？」を開いたとき（L3385）。
   */
  show(): void {
    this.#shown = true;
  }

  /**
   * 1回ぶんの操作を受ける（原型の `MENU.nav`）。
   *
   * @param commands この回に押し始めた操作（キーボードは1つ、パッドはまとめて）
   * @param sizes いまの画面の、グループごとの項目の数（上から順）。空のグループは含めない
   */
  handle(commands: readonly NavCommand[], sizes: readonly number[]): NavResult {
    if (commands.length === 0 || sizes.length === 0) return NONE;
    this.fit(sizes);
    const showed = !this.#shown;
    if (showed) {
      this.#shown = true;
      // 同じ回の移動も飲み込む（原型は A があれば、枠を出して返る。L3300）。
      if (commands.includes('confirm')) return MOVED;
    }
    if (commands.includes('back')) return { kind: 'back' };
    if (commands.includes('confirm')) return { kind: 'activate', group: this.#group, item: this.#item };
    let moved = false;
    const groups = sizes.length;
    if (commands.includes('down')) {
      this.#group = (this.#group + 1) % groups;
      moved = true;
    } else if (commands.includes('up')) {
      this.#group = (this.#group - 1 + groups) % groups;
      moved = true;
    }
    // 項目の少ないグループへ移ると、項目の番号がはみ出すことがある。
    if (moved) this.fit(sizes);
    const size = sizes[this.#group] ?? 1;
    if (commands.includes('right')) {
      this.#item = (this.#item + 1) % size;
      moved = true;
    } else if (commands.includes('left')) {
      this.#item = (this.#item - 1 + size) % size;
      moved = true;
    }
    // Start・Select・ほかのボタンは、枠を出すだけ（出ていれば何もしない）。
    return moved || showed ? MOVED : NONE;
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
