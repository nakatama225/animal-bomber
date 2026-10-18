import type { Cell, Direction } from '../../domain/core/Coord.js';
import type { CpuContext } from '../CpuContext.js';
import type { BombOption, CpuButton } from '../CpuPlan.js';

/**
 * 考える前に使う技（`AnimalTactic.beforePlan`）。
 *
 * - `button` … 押すボタン
 * - `endsTurn` … 使った tick はほかに何もしない（考え直さず、歩かず、爆弾も置かない）
 * - `when` … この tick に使うか。前の tick に同じボタンを押していたら呼ばれない（押した瞬間でしか効かないので）
 */
export interface EarlyTechnique {
  readonly button: Extract<CpuButton, 'action' | 'special'>;
  readonly endsTurn: boolean;
  readonly when: (ctx: CpuContext) => boolean;
}

/**
 * 動物ごとの CPU の戦い方。
 *
 * ## 共通の判断から動物の名前を追い出すための窓口
 *
 * 原型の CPU（cpuUpdate・planCPU）には「もぐらなら」「きつねなら」という分岐が8か所あった。
 * 動物を1匹足すたびに、共通の判断の中身を読んで書き足す必要があった。
 *
 * この版では、共通の判断（`CpuInputSource`・`ai/behaviors/`）は動物を知らない。
 * 原型の分岐は、どれも次のどこかに当たるので、それぞれをここで差し替える。
 *
 * | 差し替える点 | 原型の分岐 | 省略したとき |
 * |---|---|---|
 * | 考える前の技 | 考え直す前の、穴を掘る・舌を伸ばす・危ないときの突進 | 使わない |
 * | 歩いたあとの技 | 爆弾のあとの、狐火・粘膜爆弾・撒く | 使わない |
 * | 爆弾の置き方 | 一列に並べる | 足元に1個 |
 * | ブロックを壊しに行くときに立つ場所 | 1マス空けた手前に立つ | 壊せるブロックの隣 |
 * | 壊しに行くときに置くかの見直し | 並べる向きに壊せるブロックが無ければ置かない | 見直さない |
 * | 振る舞いの最中も考えるか | 突進の最中も考え続ける（掘る・舌の間は待つ） | 待つ |
 *
 * 戦術を書いていない動物も、省略時の振る舞いでそのまま戦える。
 *
 * ⚠️ とくぎを持っているかは、持っている印（`PlayerState.hasSpecial`）で見る。回数（`specialCharges`）では見ない。
 * 原型の CPU も cpuUpdate の L1926・L1931・L1946・L2046・L2054・L2059 で、回数ではなく chicken を見ているのと同じ。
 * 外周から戻ったプレイヤーは、回数だけが残って印が外れていることがある。回数で見ると、出ないとくぎのボタンを押し、
 * かえるは舌を伸ばさなくなる。
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
   * 考え直す前に使う技（原型 cpuUpdate の、考え直しより前の分岐）。
   *
   * `when` は毎 tick 呼ばれる。動けない間と、待つ振る舞いの最中は呼ばれない。
   */
  readonly beforePlan?: EarlyTechnique;

  /**
   * 歩いて爆弾を置いたあとに、とくぎを直に出すか（原型 cpuUpdate の最後の分岐）。
   *
   * 毎 tick 呼ばれる。滑っている間、考える前の技を使った tick、前の tick にとくぎを出したときは呼ばれない。
   */
  readonly afterMove?: (ctx: CpuContext) => boolean;

  /**
   * 爆弾の置き方。null なら足元に1個。
   *
   * @param facing この tick の移動のあとに向いている方向
   */
  readonly bombOption?: (ctx: CpuContext, facing: Direction) => BombOption | null;

  /** ブロックを壊しに行くとき、そのマスに立てば壊せるか。 */
  readonly isBreakSpot?: (ctx: CpuContext, cell: Cell) => boolean;

  /** ブロックを壊しに行く計画で「いまのマスで置く」と決めたあと、それでも置くか。 */
  readonly confirmsBreakBomb?: (ctx: CpuContext) => boolean;

  /**
   * 移動を乗っ取る自分の振る舞いの最中も、考え続けるか。
   *
   * 考え続けても、歩く・置くはゲームの側が止める。考えることで、記憶（経路・考え直すまでの間隔）が進み、
   * 考える前の技も見る。
   */
  readonly thinksDuringAction?: boolean;
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
