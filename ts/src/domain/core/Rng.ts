/**
 * ゲームの結果に影響する乱数。
 *
 * 原型では `Math.random()` が 44 箇所にあり、マップ生成・アイテムの抽選・
 * CPU の判断に加えて、画面のちらつきや粒子といった見た目だけの処理まで
 * 同じ乱数を引いていた。そのため同じ操作を与えても同じ試合にならず、
 * リプレイも、入力だけを送る通信対戦も成立しなかった。
 *
 * この版では乱数を2つに分ける。
 *
 * - `Rng`（このファイル）… 結果に影響する。種を与えれば同じ並びになる
 * - `CosmeticRng`（presentation 層）… 見た目だけ。同期しない
 *
 * **2つは層が違うため互いに import できない。** 混ざる経路を、規約ではなく
 * 依存の検査で断ってある。
 */

/**
 * 決定的な擬似乱数。
 *
 * アルゴリズムは mulberry32 を使う。32 ビットの状態を1つ持つだけで、
 * 実装が 4 行に収まり、読む人が中身を確かめられる。周期は 2^32 で、
 * 1試合で引く回数（多くても数十万回）に対して十分に長い。
 *
 * ⚠️ 暗号用途には使えない。ここで必要なのは「同じ種から同じ並びが出ること」
 * であって、予測されないことではない。
 */
export class Rng {
  /** 内部状態。32 ビット符号なし整数として扱う。 */
  #state: number;

  /**
   * この乱数を引いた回数。
   *
   * 通信対戦では 20 tick ごとに状態を突き合わせるが、状態の要約だけを
   * 比べても「どこかがずれた」までしか分からない。引いた回数も一緒に
   * 比べると「ゲームの乱数を余計に引いた／引かなかった」が切り分けられる。
   * 原因の候補が、見た目の処理の紛れ込みか、判断の分岐そのものか、に絞れる。
   */
  #calls = 0;

  constructor(seed: number) {
    // 負の数や小数を渡されても 32 ビット整数に落とす。
    this.#state = seed >>> 0;
  }

  /** この乱数を引いた回数。 */
  get calls(): number {
    return this.#calls;
  }

  /** 内部状態。リプレイの保存と突き合わせに使う。 */
  get state(): number {
    return this.#state;
  }

  /** 0 以上 1 未満の小数を返す。 */
  next(): number {
    this.#calls += 1;
    this.#state = (this.#state + 0x6d2b79f5) >>> 0;
    let t = this.#state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  /** 0 以上 `maxExclusive` 未満の整数を返す。 */
  int(maxExclusive: number): number {
    return Math.floor(this.next() * maxExclusive);
  }

  /** `min` 以上 `maxExclusive` 未満の整数を返す。 */
  range(min: number, maxExclusive: number): number {
    return min + this.int(maxExclusive - min);
  }

  /** 確率 `probability`（0〜1）で true を返す。 */
  chance(probability: number): boolean {
    return this.next() < probability;
  }

  /**
   * 配列から1つ選ぶ。空の配列を渡してはいけない。
   *
   * 呼び出し側が空でないことを確かめてから渡す設計にしている。
   * 「空なら null を返す」形にすると、その null を扱う分岐が
   * 呼び出し側すべてに増えるため。
   */
  pick<T>(items: readonly T[]): T {
    if (items.length === 0) {
      throw new Error('空の配列からは選べない');
    }
    // 添字は int() が length 未満を保証するので範囲内。
    return items[this.int(items.length)] as T;
  }

  /**
   * 配列を混ぜる（Fisher-Yates）。元の配列を書き換える。
   *
   * ⚠️ `sort(() => rng.next() - 0.5)` は使わない。比較関数が
   * 全順序になっていないため、結果が処理系の並べ替え実装に依存する。
   * 原型にこの書き方が1か所あった。
   */
  shuffle<T>(items: T[]): void {
    for (let i = items.length - 1; i > 0; i -= 1) {
      const j = this.int(i + 1);
      // i はループ条件、j は int() の上限で、どちらも範囲内が保証されている。
      const a = items[i] as T;
      const b = items[j] as T;
      items[i] = b;
      items[j] = a;
    }
  }

  /**
   * いまの状態を引き継いだ別の乱数を作る。
   *
   * 「この先どうなるか」を試算したいときに使う。元の乱数は進まない。
   * 引いた回数は 0 から数え直す。
   */
  clone(): Rng {
    return new Rng(this.#state);
  }
}
