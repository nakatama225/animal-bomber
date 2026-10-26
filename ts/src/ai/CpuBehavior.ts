import type { CpuContext } from './CpuContext.js';
import { STAY, type CpuPlan } from './CpuPlan.js';

/**
 * CPU の判断の規則1つ。
 *
 * 自分の出番だと思えば計画を返し、そうでなければ null を返して次に譲る。
 *
 * ## 規則を優先順に並べて、先頭から試す
 *
 * 原型の判断は、140 行の関数の中に if を順に並べたものだった。
 * 規則を1つ足したり外したりするには、関数全体を読んで、どこに差し込むと
 * どの分岐が飛ばされるかを確認する必要があった。
 *
 * この版では規則を1つずつ独立させ、配列に並べる。配列の順番が
 * そのまま優先順位になる。
 *
 * - 規則を試しに外す … 配列から1行消す
 * - 規則を試しに足す … 配列に1行足す
 * - 優先順位を変える … 行を入れ替える
 *
 * どの規則も、ほかの規則の存在を知らない。
 * `tests/ai/cpu.test.ts` に、規則を1つ足すと CPU の振る舞いが
 * どう変わるかを確認する例がある。
 */
export interface CpuBehavior {
  /** 記録と説明のための名前。 */
  readonly name: string;
  /** 自分の出番なら計画を返す。出番でなければ null。 */
  readonly decide: (ctx: CpuContext) => CpuPlan | null;
}

/** 規則を先頭から試し、最初に返ってきた計画を採る。どれも返さなければ留まる。 */
export function decide(chain: readonly CpuBehavior[], ctx: CpuContext): CpuPlan {
  for (const behavior of chain) {
    const plan = behavior.decide(ctx);
    if (plan !== null) return plan;
  }
  return STAY;
}
