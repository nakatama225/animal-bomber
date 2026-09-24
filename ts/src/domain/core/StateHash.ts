/**
 * 試合の状態を、比べられる1つの数値に要約する。
 *
 * 使いどころは2つある。
 *
 * - **リプレイの検証**：同じ入力を2回流して、同じ要約になるか
 * - **通信対戦**：一定の tick ごとに参加者どうしで突き合わせ、ずれを早く見つける
 *
 * ずれは、起きた瞬間には目に見えない。数十秒たってから「相手の画面では
 * 当たっているのに自分の画面では外れている」という形で現れる。
 * そこから原因まで遡るのは難しいので、**ずれた直後の tick で気づく**ための
 * 仕組みを先に置く。
 *
 * アルゴリズムは FNV-1a の 32 ビット版。衝突しない保証はないが、
 * ここで必要なのは「違うものが同じ値になりにくいこと」であって、
 * 改竄を防ぐことではない。実装が短く、読んで確かめられることを優先した。
 */

const FNV_OFFSET_BASIS = 0x811c9dc5;
const FNV_PRIME = 0x01000193;

/**
 * 要約を組み立てる。
 *
 * 値を混ぜていく順番がそのまま結果を決めるので、**混ぜる順序は
 * 実装ごとに固定する**。順序が変わると別の値になり、ずれていないのに
 * ずれたと判定される。
 */
export class StateHasher {
  #hash = FNV_OFFSET_BASIS;

  /** 32 ビット整数を混ぜる。 */
  int(value: number): this {
    let v = value | 0;
    for (let i = 0; i < 4; i += 1) {
      this.#hash = Math.imul(this.#hash ^ (v & 0xff), FNV_PRIME) >>> 0;
      v >>>= 8;
    }
    return this;
  }

  /**
   * 小数を混ぜる。
   *
   * ビットのまま取り出して混ぜる。丸めてから混ぜると、
   * わずかなずれを見逃してしまう。ずれは小さいうちに見つけたい。
   */
  float(value: number): this {
    const buffer = new ArrayBuffer(8);
    new Float64Array(buffer)[0] = value;
    const words = new Uint32Array(buffer);
    return this.int(words[0] as number).int(words[1] as number);
  }

  /** 真偽値を混ぜる。 */
  bool(value: boolean): this {
    return this.int(value ? 1 : 0);
  }

  /** 文字列を混ぜる。 */
  text(value: string): this {
    for (let i = 0; i < value.length; i += 1) {
      this.#hash = Math.imul(this.#hash ^ value.charCodeAt(i), FNV_PRIME) >>> 0;
    }
    // 長さも混ぜる。混ぜないと "ab" + "c" と "a" + "bc" が同じ値になる。
    return this.int(value.length);
  }

  /** 組み立てた要約。 */
  get value(): number {
    return this.#hash >>> 0;
  }

  /** 見比べやすい 8 桁の十六進表記。 */
  get hex(): string {
    return this.value.toString(16).padStart(8, '0');
  }
}
