import type { CpuBehavior } from '../CpuBehavior.js';
import { ATTACK_IN_LINE } from './AttackInLine.js';
import { BREAK_BLOCKS } from './BreakBlocks.js';
import { COLLECT_ITEM } from './CollectItem.js';
import { FLEE } from './Flee.js';
import { HUNT } from './Hunt.js';
import { WANDER } from './Wander.js';

/**
 * 標準の判断の並び。上にあるものほど優先する。
 *
 * 身の安全がいちばん上、うろつくのがいちばん下。
 * 相手を狙う規則がアイテムより上にあるのは、射線に入った相手は
 * 次の瞬間には外れているから。アイテムは逃げない。
 */
export const DEFAULT_CHAIN: readonly CpuBehavior[] = [
  FLEE,
  ATTACK_IN_LINE,
  COLLECT_ITEM,
  HUNT,
  BREAK_BLOCKS,
  WANDER,
];
