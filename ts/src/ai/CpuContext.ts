import type { Ability } from '../domain/abilities/Ability.js';
import { abilityOf } from '../domain/abilities/registry.js';
import { cellOf, sameCell, type Cell } from '../domain/core/Coord.js';
import type { Rng } from '../domain/core/Rng.js';
import { secondsToTicks } from '../domain/core/Tick.js';
import type { PassesThrough } from '../domain/query/BoardQuery.js';
import type { DangerMap } from '../domain/query/DangerMap.js';
import { findPath, type PathOptions } from '../domain/query/PathFinder.js';
import type { PlayerState } from '../domain/state/PlayerState.js';
import { isAlive } from '../domain/state/PlayerState.js';
import type { WorldState } from '../domain/state/WorldState.js';
import type { CpuLevel } from './CpuLevel.js';
import type { CpuMemory } from './CpuMemory.js';
import type { CpuButton } from './CpuPlan.js';

/** とくぎの抽選に外れたあと、次に抽選するまで。 */
const SKILL_RETRY = secondsToTicks(0.4);

/**
 * CPU が1回の判断で見るものと、使える機能。
 *
 * ## 何を書き換えてよいか
 *
 * - `world`（試合の状態）… **読むだけ**。書き換えると、入力を返す前に
 *   試合が進んでしまい、リプレイと通信対戦の前提が崩れる
 * - `memory`（CPU 自身の記憶）… 書き換えてよい
 * - `rng`（CPU 専用の乱数）… 取り出してよい。試合の乱数とは別物なので、
 *   CPU が何回取り出しても盤面やアイテムの抽選は変わらない
 *
 * 1 tick ごとに作り直す。前の tick の値を持ち越さない。
 */
export class CpuContext {
  readonly ability: Ability;
  readonly foes: readonly PlayerState[];

  constructor(
    readonly world: Readonly<WorldState>,
    readonly me: PlayerState,
    readonly here: Cell,
    readonly danger: DangerMap,
    readonly inDanger: boolean,
    readonly level: CpuLevel,
    readonly memory: CpuMemory,
    readonly rng: Rng,
  ) {
    this.ability = abilityOf(me.animal);
    this.foes = world.players.filter((p) => p.id !== me.id && isAlive(p));
  }

  /**
   * 壊せるブロックを抜けられるかの判定。動物によっては無い。
   *
   * 盤面への問い合わせ（`isSolidFor` / `findPath`）へ渡す形にしてある。
   */
  get passesThrough(): PassesThrough | undefined {
    return this.ability.passesThrough?.bind(this.ability);
  }

  /** 爆弾を狙う判断をしてよいか。直前に置けないと分かった場合は控える。 */
  get canBomb(): boolean {
    return this.memory.bombBan <= 0;
  }

  /**
   * この tick にそのボタンを押せるか。
   *
   * ゲームの側は「前の tick は押していない」ときだけ押したと読む。前の tick に押したボタンは、
   * この tick に押しても無効。
   */
  canPress(button: CpuButton): boolean {
    return !this.me.previousInput[button];
  }

  /**
   * 攻めの判断に踏み切るか。
   *
   * 強さの表の `aggression` の確率で true。弱い CPU は攻めをよく見送る。
   */
  willing(): boolean {
    return this.rng.chance(this.level.aggression);
  }

  /**
   * とくぎを使うか。
   *
   * ⚠️ 外れたら少し待つ。使える場面で毎 tick 抽選すると、確率 0.7 でも
   * 1秒のうちにほぼ確実に当たり、実質 100% になる。待つことで
   * 「弱い CPU はとくぎを使い損ねる」が実際に起きる。
   */
  skillReady(): boolean {
    if (this.memory.skillCool > 0) return false;
    if (this.rng.chance(this.level.skillUse)) return true;
    this.memory.skillCool = SKILL_RETRY;
    return false;
  }

  /**
   * 自分の足で歩いて、条件を満たすマスまでの経路。
   *
   * 壊せるブロックを抜けられるかどうかは動物ごとの能力に従う。
   */
  pathTo(
    goal: (cell: Cell, distance: number) => boolean,
    options: Omit<PathOptions, 'passesThrough'>,
  ): Cell[] | null {
    const passesThrough = this.passesThrough;
    const full: PathOptions =
      passesThrough === undefined ? options : { ...options, passesThrough };
    return findPath(this.world, this.me, this.here, goal, full);
  }

  /** そのマスに相手が立っているか。 */
  foeAt(cell: Cell): boolean {
    return this.foes.some((foe) => sameCell(cellOf(foe.position), cell));
  }

  /**
   * いちばん近い相手までの、歩ける経路の長さ。届かなければ無限大。
   *
   * ⚠️ マンハッタン距離（縦横の差の和）で見ない。壁越しの相手を
   * 「近い」と誤って判断し、とくぎを無駄に撃つ。原型で、壁の向こうの
   * 相手へ飛び道具を撃ち続けた原因がこれだった。
   */
  foePathDistance(maxDistance: number): number {
    if (this.foes.length === 0) return Number.POSITIVE_INFINITY;
    const path = this.pathTo((cell) => this.foeAt(cell), { maxDistance });
    return path === null ? Number.POSITIVE_INFINITY : path.length;
  }

  /** 盤面にある自分の爆弾の数。 */
  get liveOwnBombs(): number {
    return this.world.bombs.filter((bomb) => bomb.owner === this.me.id).length;
  }
}
