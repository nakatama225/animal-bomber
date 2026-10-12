import { tick, type Tick } from '../core/Tick.js';

/**
 * プレイヤーに一時的にかかっている状態。
 *
 * 良いもの（とくぎの溜め）も悪いもの（滑る・泣いて動けない）も同じ器で扱う。
 * 原型ではこれらが `p.effects.slide` のような個別のフィールドとして
 * あちこちに散っており、たとえば突進の状態だけで 11 箇所に判定があった。
 */

/** かかりうる状態の種類。**この一覧が閉じていることが網羅性の土台になる。** */
export type EffectKind =
  /** バナナ。向いている方向へ滑り続ける。 */
  | 'slide'
  /** たまねぎ。涙で動けない。 */
  | 'stun'
  /** 操作の左右上下が反転する。 */
  | 'reverse'
  /** 爆弾を置けない。 */
  | 'nobomb'
  /** 止まれない。歩き出したら壁まで進む。 */
  | 'runaway'
  /** 爆風が1マスに落ちる。 */
  | 'weak'
  /** 勝手に爆弾を置いてしまう。 */
  | 'autobomb'
  /** 極端に遅くなる。 */
  | 'slow'
  /**
   * 落とし穴にはまって動けない。
   *
   * ⚠️ たまねぎの 'stun' とは分けて持つ。どちらも動けないが、はまっている間は爆弾を
   * 置けず、泣いている間は置ける（動けない2つのうち、原型の canPlaceBomb が見るのは落とし穴だけ）。
   * はまっている間は別の穴にも落ちない。1つにまとめると、この2つが見分けられない。
   */
  | 'pitfall'
  /**
   * とくぎを放つ瞬間に跳び上がっている（原型の、とくぎで跳ぶ状態）。爆風・追いかける炎・体当たりの傷が当たらず
   * （`isBlastProof`）、葱も当たらない（`isUntouchable`）。動けて、爆弾も技も出せる。
   *
   * ⚠️ 被弾のあとの無敵（`invulnerableUntil`）とは分けて持つ。被弾のあとの無敵は点滅して見せ、
   * こちらは跳んで見せる。長さも違う（被弾のあと 1.25 秒、跳ぶのは 1 秒）。
   */
  | 'leap'
  /**
   * 周りに撒いている最中の身ぶり（原型の poro）。見た目と状態の表示のためだけの状態で、何も止めない
   * （歩けて、爆弾も技も出せる）。撒く本体は盤面の側の物が進めるので、これが切れても撒くのは続く。
   */
  | 'scattering';

/** すべての種類を、いつも同じ順で並べたもの。 */
export const EFFECT_KINDS: readonly EffectKind[] = [
  'slide',
  'stun',
  'reverse',
  'nobomb',
  'runaway',
  'weak',
  'autobomb',
  'slow',
  'pitfall',
  'leap',
  'scattering',
];

/**
 * かかっている状態と、その残り時間。
 *
 * ⚠️ 中身を `for...in` で走査しない。列挙の順序が保証されないため、
 * 同じ状態でも処理の順が変わりうる。走査には `EFFECT_KINDS` を使う。
 */
export class EffectBag {
  readonly #remaining = new Map<EffectKind, Tick>();

  /** その状態がかかっているか。 */
  has(kind: EffectKind): boolean {
    return (this.#remaining.get(kind) ?? 0) > 0;
  }

  /** 残り時間。かかっていなければ 0。 */
  remaining(kind: EffectKind): Tick {
    return this.#remaining.get(kind) ?? tick(0);
  }

  /**
   * 状態をかける。すでにかかっていれば残り時間を足す（うんこでかかる状態）。
   *
   * ⚠️ うんこの状態は、上書きではなく加算にしている（原型も 2026-08-23 から加算）。
   * 原型が上書きだった頃は、悪い状態をいくつ踏んでも常に1つぶんの時間で済んでしまい、
   * 「踏むコスト」が頭打ちになっていた。その結果、CPU が悪いアイテムの密集地帯へ
   * 平然と突っ込んでくる挙動が出た。バナナとたまねぎは、原型のいまも上書き（`set`）。
   *
   * @param cap 積み上げの上限。青天井にすると復帰できなくなる
   */
  add(kind: EffectKind, duration: Tick, cap: Tick): void {
    const next = Math.min(this.remaining(kind) + duration, cap);
    this.#remaining.set(kind, tick(next));
  }

  /**
   * 状態をかける。すでにかかっていれば、残り時間を `duration` に置き換える（足さない）。
   *
   * バナナ（滑る）とたまねぎ（泣く）はこちら（原型の applyItem も、残り時間を代入する）。
   */
  set(kind: EffectKind, duration: Tick): void {
    if (duration <= 0) this.#remaining.delete(kind);
    else this.#remaining.set(kind, duration);
  }

  /** 状態を解く。 */
  clear(kind: EffectKind): void {
    this.#remaining.delete(kind);
  }

  /** 1 tick ぶん時間を進め、切れたものを外す。 */
  advance(): void {
    for (const kind of EFFECT_KINDS) {
      const left = this.#remaining.get(kind);
      if (left === undefined) continue;
      if (left <= 1) this.#remaining.delete(kind);
      else this.#remaining.set(kind, tick(left - 1));
    }
  }

  /** かかっているものを、決まった順で並べる。 */
  active(): EffectKind[] {
    return EFFECT_KINDS.filter((kind) => this.has(kind));
  }

  /** 状態の要約に混ぜるための値。 */
  encode(): string {
    return EFFECT_KINDS.map((kind) => `${this.remaining(kind)}`).join(',');
  }

  /** 複製する。試算に使う。 */
  clone(): EffectBag {
    const copy = new EffectBag();
    for (const kind of EFFECT_KINDS) {
      const left = this.#remaining.get(kind);
      if (left !== undefined) copy.#remaining.set(kind, left);
    }
    return copy;
  }
}
