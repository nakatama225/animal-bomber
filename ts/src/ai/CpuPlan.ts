import type { Cell } from '../domain/core/Coord.js';
import type { HypotheticalBomb } from '../domain/query/DangerMap.js';

/**
 * CPU が押すボタン。
 *
 * - `bomb` … 爆弾のボタン（足元に1個）
 * - `action` … 技のボタンを押した瞬間（通常技）
 * - `special` … とくぎを直に出すボタン（原型の CPU が useSpecial を直に呼んでいたのと同じ出し方。`PlayerInput.special`）
 *
 * CPU は技のボタンを押し続けない。原型の CPU は長押しを使わず、とくぎは関数を直に呼んでいた。
 */
export type CpuButton = 'bomb' | 'action' | 'special';

/**
 * 爆弾の置き方。
 *
 * 足元に1個置くのが基本だが、動物によっては別の置き方を持つ
 * （正面へ一列に並べる、など）。どの置き方でも、
 * 「置いたあと盤面に増える爆弾」と「そのために押すボタン」の組で表す。
 * 共通の判断は、増える爆弾だけを見て逃げ切れるかを決める。
 */
export interface BombOption {
  readonly bombs: readonly HypotheticalBomb[];
  readonly button: Extract<CpuButton, 'bomb' | 'action'>;
}

/**
 * CPU がいま何をしようとしているか。
 *
 * 画面に出すものではなく、判断を続けるかどうかの手がかりに使う。
 * たとえば「逃げている最中」なら、行き先が危なくなった瞬間に考え直す。
 */
export type CpuMode =
  /** まだ何も決めていない。 */
  | 'idle'
  /** 爆風の届くマスから離れる。 */
  | 'flee'
  /** 飛んでくる葱の射線から外れる。 */
  | 'dodge'
  /** 射線に入った相手を狙う。 */
  | 'attack'
  /** アイテムを拾いに行く。 */
  | 'item'
  /** 相手に近づく。 */
  | 'hunt'
  /** ブロックを壊しに行く。 */
  | 'dig'
  /** やることが無いので歩き回る。 */
  | 'wander';

/**
 * 1回の判断の結果。
 *
 * 「どこへ歩くか」と「着いたら爆弾を置きたいか」だけを持つ。
 * 実際にボタンをどう押すかは `CpuInputSource` が決める。
 * 判断と操作を分けておくと、判断の規則を足し引きしても
 * ボタンの押し方（押した瞬間の扱いなど）に触れずに済む。
 */
export interface CpuPlan {
  readonly mode: CpuMode;
  /** 次のマスから目的地までの並び。空ならその場に留まる。 */
  readonly path: readonly Cell[];
  /** いまいるマスで爆弾を置きたいか。 */
  readonly wantBomb: boolean;
}

/** 何もしない計画。 */
export const STAY: CpuPlan = Object.freeze({ mode: 'idle', path: [], wantBomb: false });
