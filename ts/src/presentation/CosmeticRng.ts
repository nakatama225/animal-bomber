/**
 * 見た目だけの乱数。**同期しない。**
 *
 * 爆風のちらつき、粒子の飛び散り方、画面の揺れ。参加者どうしで
 * 違っていても、誰も気づかず、誰も損をしないもの。
 *
 * これを `Rng`（ルールの層）と分ける理由は、混ざると
 * **同じ入力で同じ試合にならなくなる**ことにある。原型では両方が
 * `Math.random()` を共有していたため、粒子を1つ多く出しただけで
 * その後の全ての抽選がずれた。
 *
 * ⚠️ この2つは層が違うため、互いに import できない。ルールの層から
 * この乱数を使おうとすると、依存の検査が落ちる
 * （`.dependency-cruiser.cjs` の「見た目の乱数をルールの層へ持ち込まない」）。
 *
 * 中身が `Math.random` そのままで構わないのは、同期も再現も要らないから。
 * ここに凝った実装を置く理由はない。
 */
export class CosmeticRng {
  /** 0 以上 1 未満の小数。 */
  next(): number {
    return Math.random();
  }

  /** 0 以上 `maxExclusive` 未満の整数。 */
  int(maxExclusive: number): number {
    return Math.floor(this.next() * maxExclusive);
  }

  /** `min` 以上 `max` 未満の小数。 */
  between(min: number, max: number): number {
    return min + this.next() * (max - min);
  }

  /** 確率 `probability`（0〜1）で true。 */
  chance(probability: number): boolean {
    return this.next() < probability;
  }

  /** `-spread` 以上 `spread` 未満の小数。揺らぎを付けるのに使う。 */
  jitter(spread: number): number {
    return this.between(-spread, spread);
  }
}
