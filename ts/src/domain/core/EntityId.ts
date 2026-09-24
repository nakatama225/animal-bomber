/**
 * 盤面に置かれるものの識別子。
 *
 * 爆弾・アイテム・爆風・落とし穴などを指す。単なる数値と混ざらないよう
 * 型を分けてある。
 *
 * 発番は連番で、試合の開始時に 1 から数え直す。乱数を使わないのは、
 * 同じ入力なら同じ識別子になることを保つため。リプレイと通信対戦で
 * 「同じものを指しているか」を識別子だけで確かめられる。
 */

/** 盤面上のものを指す識別子。 */
export type EntityId = number & { readonly __entityId: unique symbol };

/**
 * 識別子を順に発番する。
 *
 * 試合ごとに1つ持つ。状態の一部なので、リプレイのときは同じ順で
 * 同じ番号が出る。
 */
export class IdSource {
  #next = 1;

  /** 次の識別子を取り出す。 */
  take(): EntityId {
    const id = this.#next as EntityId;
    this.#next += 1;
    return id;
  }

  /** いままでに発番した数。状態の突き合わせに使う。 */
  get issued(): number {
    return this.#next - 1;
  }
}
