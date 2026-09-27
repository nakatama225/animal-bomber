import type { Cell } from '../../domain/core/Coord.js';
import type { BombOption } from '../BombPlacement.js';
import type { ButtonMacro } from '../ButtonMacro.js';
import type { CpuContext } from '../CpuContext.js';

/**
 * 動物ごとの CPU の戦い方。
 *
 * ## 共通の判断から動物の名前を追い出すための窓口
 *
 * 原型の CPU には「もぐらなら」「きつねなら」という分岐が8か所あった。
 * 動物を1匹足すたびに、共通の判断の中身を読んで書き足す必要があった。
 *
 * この版では、共通の判断（`ai/behaviors/`）は動物を知らない。
 * 動物によって違うのは次の3点だけで、それぞれをここで差し替える。
 *
 * | 差し替える点 | 省略したとき |
 * |---|---|
 * | 爆弾の置き方 | 足元に1個 |
 * | ブロックを壊しに行くときに立つ場所 | 壊せるブロックの隣 |
 * | 判断とは別に技を使う機会 | 使わない |
 *
 * 戦術を書いていない動物も、省略時の振る舞いでそのまま戦える。
 *
 * ## ⚠️ ルールの層（`Ability`）に置かない理由
 *
 * 「いつ突進するか」はゲームのルールではなく、CPU の考え方にすぎない。
 * 人間は同じ能力を別の場面で使う。ルールの側に置くと、将来 CPU を
 * 機械学習などに差し替えたときにも、使われない判断がルールの層に残る。
 */
export interface AnimalTactic {
  /** どの動物の戦い方か。能力の鍵と同じ文字列。 */
  readonly animal: string;

  /**
   * 爆弾の置き方の候補を、試す順に返す。
   *
   * 共通の判断は先頭から順に「逃げ切れるか」を試し、最初に通ったものを使う。
   */
  readonly bombOptions?: (ctx: CpuContext) => BombOption[];

  /** ブロックを壊しに行くとき、そのマスに立てば壊せるか。 */
  readonly isBreakSpot?: (ctx: CpuContext, cell: Cell) => boolean;

  /**
   * 判断の周期とは別に、毎 tick 技を使う機会を見る。
   *
   * 使うならボタンの押し方を返す。ボタン操作の途中では呼ばれない。
   */
  readonly reflex?: (ctx: CpuContext) => ButtonMacro | null;
}

/** 戦術を書いていない動物に使う、省略時の戦い方。 */
export const PLAIN_TACTIC: AnimalTactic = { animal: '' };

const tactics = new Map<string, AnimalTactic>();

/** 戦い方を登録する。同じ動物を二度登録したら後のほうが勝つ。 */
export function registerTactic(tactic: AnimalTactic): void {
  tactics.set(tactic.animal, tactic);
}

/** 登録された戦い方を引く。無ければ undefined。 */
export function lookupTactic(animal: string): AnimalTactic | undefined {
  return tactics.get(animal);
}
