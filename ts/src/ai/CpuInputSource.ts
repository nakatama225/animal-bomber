import { cellOf, type Direction } from '../domain/core/Coord.js';
import { Rng } from '../domain/core/Rng.js';
import { secondsToTicks } from '../domain/core/Tick.js';
import type { InputSource } from '../domain/input/InputSource.js';
import { IDLE_INPUT, type PlayerInput } from '../domain/input/PlayerInput.js';
import { isSolidFor, playerById } from '../domain/query/BoardQuery.js';
import { DangerMap } from '../domain/query/DangerMap.js';
import { cellsTouchedBy } from '../domain/query/Hitbox.js';
import type { PlayerId, PlayerState } from '../domain/state/PlayerState.js';
import { isAlive, isFrozen } from '../domain/state/PlayerState.js';
import type { WorldState } from '../domain/state/WorldState.js';
import { decideBomb, footBomb } from './BombPlacement.js';
import type { MacroStep } from './ButtonMacro.js';
import { decide, type CpuBehavior } from './CpuBehavior.js';
import { CpuContext } from './CpuContext.js';
import type { CpuLevel } from './CpuLevel.js';
import { freshMemory, type CpuMemory } from './CpuMemory.js';
import { BLIND_MIN_SECONDS, BLIND_SPREAD_SECONDS, SHARP_THINK } from './margins.js';
import { compensateReverse, directionAlong } from './PathFollower.js';
import { DEFAULT_CHAIN } from './behaviors/DefaultChain.js';
import { NegibonPilot } from './NegibonPilot.js';
import { tacticOf } from './tactics/registry.js';

/**
 * CPU の操作の出どころ。
 *
 * キーボードやゲームパッドと同じく、1 tick ごとに `PlayerInput` を返すだけ。
 * ゲーム本体からは人間と区別がつかない。
 *
 * ## 1 tick の流れ
 *
 * 1. 危険の地図を作り、いま立っているマスが危ないかを見る
 * 2. 動物ごとの戦い方に、技を使う機会があるかを聞く
 * 3. 判断の間隔が来ていれば、規則の連鎖で次の計画を決める
 * 4. 爆弾を置きたい計画なら、逃げ切れるかを確かめて置く
 * 5. 計画の経路を、押す向きに変える
 *
 * ## ⚠️ 乱数は CPU 専用のものを持つ
 *
 * 試合の乱数（`world.rng`）を引かない。引くと、CPU が何回考えたかで
 * アイテムの抽選が変わり、同じ操作でも同じ試合にならなくなる。
 * `Math.random` も使わない（lint で禁じてある）。CPU の判断も種から
 * 決まるので、同じ種・同じ盤面なら CPU は毎回同じ手を指す。
 * 通信対戦で各端末が CPU を動かしても、全員が同じ手を得る。
 */
export class CpuInputSource implements InputSource {
  readonly #level: CpuLevel;
  readonly #rng: Rng;
  readonly #chain: readonly CpuBehavior[];
  #world: Readonly<WorldState> | null = null;
  /** 最後に見た盤面が延長戦に入っていたか。 */
  #sawSuddenDeath = false;
  /** 最後に見たとき、自分が盤面にいたか。外周から戻ったことを知るのに使う。 */
  #onBoard = true;
  /** 外周にいる間の操縦。外周へ回るたびに作り直す。 */
  #pilot: NegibonPilot | null = null;
  #memory: CpuMemory;

  /**
   * @param seed CPU の判断に使う乱数の種。`cpuSeed()` で試合の種から作る
   * @param chain 判断の規則の並び。省略すると標準の並び
   */
  constructor(
    readonly playerId: PlayerId,
    level: CpuLevel,
    seed: number,
    chain: readonly CpuBehavior[] = DEFAULT_CHAIN,
  ) {
    this.#level = level;
    this.#rng = new Rng(seed);
    this.#chain = chain;
    this.#memory = freshMemory(this.#rng);
  }

  /** この CPU の強さ。通信対戦で、プレイヤーごとの強さが届いたかを確かめるのに使う。 */
  get level(): CpuLevel {
    return this.#level;
  }

  /** いまの記憶。テストで判断の中身を確かめるために公開している。 */
  get memory(): Readonly<CpuMemory> {
    return this.#memory;
  }

  next(world: Readonly<WorldState>): PlayerInput {
    // ラウンドが変わると盤面が作り直される。前のラウンドの経路を捨てる。
    // 延長戦に入ったときも、全員が開始位置へ移って盤面が片付くので同じく捨てる。
    if (world !== this.#world || world.suddenDeath !== this.#sawSuddenDeath) {
      this.#world = world;
      this.#sawSuddenDeath = world.suddenDeath;
      this.#memory = freshMemory(this.#rng);
      this.#onBoard = true;
      this.#pilot = null;
    }

    const me = playerById(world, this.playerId);
    if (me === undefined) return IDLE_INPUT;
    if (me.life.kind === 'negibon') {
      this.#onBoard = false;
      this.#pilot ??= new NegibonPilot();
      return this.#pilot.next(world, me.life);
    }
    this.#pilot = null;
    if (!isAlive(me)) {
      this.#onBoard = false;
      return IDLE_INPUT;
    }
    // 外周から葱を当てて戻ると、当てた相手の位置へ移る。倒れる前の道筋は使えない。
    if (!this.#onBoard) {
      this.#onBoard = true;
      this.#memory = freshMemory(this.#rng);
    }

    const memory = this.#memory;
    countDown(memory);

    // 技の最中は、技のボタンを押しても効かない（ゲームの側が見ていない）。
    // 移動まで乗っ取る技なら、何もせず終わるのを待つ。
    // ⚠️ 移動を乗っ取らない技（撒きながら逃げる、など）の最中は歩ける。
    // ここで一律に待つと、危ないマスで2秒固まって倒れる。
    if (me.action !== null) {
      memory.macro = null;
      if (me.action.drivesMovement) return IDLE_INPUT;
    }

    const here = cellOf(me.position);
    const danger = DangerMap.of(world);
    // 立っているマスだけでなく、体がはみ出している隣のマスも見る。
    const touching = cellsTouchedBy(me.position);
    const inDanger = this.#noticeDanger(touching.some((cell) => !danger.isSafe(cell)));
    const ctx = new CpuContext(world, me, here, danger, inDanger, this.#level, memory, this.#rng);

    // 泣いている・落とし穴にはまっている間は何もしない（原型の CPU も同じ）。押している途中の
    // ボタンも離し、手順は捨てる。動けない間に離しても通常技は出ない（`ActionSystem` の説明）ので、
    // 離して別の技に化けることはない。動けるようになったら考え直す。
    if (isFrozen(me)) {
      memory.macro = null;
      return IDLE_INPUT;
    }

    this.#keepSafeWhileHolding(ctx);
    // ⚠️ 技のボタンが「離されて数え直された」状態（押している長さが 0）のときだけ
    // 技を使う。ゲームの側は押した長さが長押しのしきい値に**ちょうど届いた瞬間**に
    // とくぎを出すので、数え直される前に押し始めるとしきい値を飛び越して不発になる。
    // これが起きるのは2つの場面。
    // - ラウンドの開始時。ボタンが固定されていて、一度離すまで数えられない（値が負）
    // - 技が終わった直後。技の最中はゲームの側がボタンを見ないので、長さが残っている
    const buttonReady = me.actionHeld === 0 && me.action === null;
    if (memory.macro === null && buttonReady) {
      memory.macro = tacticOf(me.animal).reflex?.(ctx) ?? null;
    }

    this.#replanIfNeeded(ctx);

    // 技の最中に置けるかは、その技が決める。
    const canPlaceNow = me.action === null || me.action.canPlaceBomb;
    if (memory.macro === null && canPlaceNow) {
      const options =
        (buttonReady ? tacticOf(me.animal).bombOptions?.(ctx) : undefined) ?? [footBomb(ctx)];
      memory.macro = decideBomb(ctx, options);
    }

    const step = takeStep(memory);
    const walk = step?.still === true ? null : directionAlong(me, memory.path);
    return compose(me, step, step?.face ?? walk);
  }

  /**
   * 危ないマスに立っているかを、強さに応じて見落とす。
   *
   * 見落としは一度決めたらしばらく続ける。判断のたびに抽選し直すと、
   * 気づいたり気づかなかったりが毎 tick 入れ替わり、動きが震える。
   */
  #noticeDanger(actual: boolean): boolean {
    const memory = this.#memory;
    if (!actual) {
      memory.blind = 0;
      return false;
    }
    if (memory.blind > 0) {
      memory.blind -= 1;
      return false;
    }
    if (this.#rng.chance(this.#level.sloppy)) {
      memory.blind = secondsToTicks(BLIND_MIN_SECONDS + this.#rng.next() * BLIND_SPREAD_SECONDS);
      return false;
    }
    return true;
  }

  /**
   * 立ち止まって長押ししている最中に危なくなったら、立ち止まるのをやめ、押し続けたまま逃げる。
   *
   * 長押しを途中で打ち切る安全な手は無い。離すと、押して離す技を持つ動物はその技が、
   * 持たない動物はとくぎが出る（`ActionSystem`）。押し続ければ、しきい値に届いた所でとくぎが出る。
   *
   * ⚠️ 長押しのときだけ。押して離すだけの技は、次の tick に出し切る。
   * そこで歩かせると向きが変わり、技が逃げる向きへ出る（一列に並べる技なら、
   * 自分の逃げ道に爆弾を並べてしまう）。
   */
  #keepSafeWhileHolding(ctx: CpuContext): void {
    const macro = ctx.memory.macro;
    if (macro === null || !macro.isHold || !ctx.inDanger || !macro.holdsStill) return;
    macro.allowMovement();
  }

  /** 判断の間隔が来ていれば、次の計画を決める。 */
  #replanIfNeeded(ctx: CpuContext): void {
    const memory = ctx.memory;
    if (ctx.inDanger) {
      if (memory.mode !== 'flee' || !fleeStillWorks(ctx)) {
        // 危なくなったのに逃げていない、または逃げ道が使えなくなった。すぐ考え直す。
        memory.thinkIn = 0;
      } else {
        // ⚠️ 逃げ道が使えるうちは考え直さない。マスの境目に立っていると、
        // どちらのマスから探すかで逃げ道が入れ替わり、1 tick ごとに
        // 向きが反転して逃げ遅れる。決めた逃げ道を最後まで使う。
        return;
      }
    }
    if (memory.thinkIn > 0) return;

    // 危ないときだけ判断を詰める強さもある。ふだんは表の間隔のまま。
    const base = ctx.inDanger && ctx.level.sharp ? SHARP_THINK : ctx.level.thinkInterval;
    memory.thinkIn = Math.max(1, Math.round(base * (1 + memory.jitter)));

    const plan = decide(this.#chain, ctx);
    memory.mode = plan.mode;
    memory.path = [...plan.path];
    memory.wantBomb = plan.wantBomb;
  }
}

/**
 * いま持っている逃げ道が、まだ使えるか。
 *
 * 行き先がまだ安全で、次の一歩が塞がれていなければ使える。
 * 行き先が空なら、立っているマスが安全で中央へ寄っている最中なので使える。
 */
function fleeStillWorks(ctx: CpuContext): boolean {
  const path = ctx.memory.path;
  const goal = path[path.length - 1];
  if (goal === undefined) return ctx.danger.isSafe(ctx.here);
  if (!ctx.danger.isSafe(goal)) return false;
  const next = path[0];
  if (next === undefined) return false;
  return !isSolidFor(ctx.world, next, ctx.me, ctx.passesThrough);
}

/** 試合の種とプレイヤー番号から、CPU の判断に使う乱数の種を作る。 */
export function cpuSeed(matchSeed: number, playerId: PlayerId): number {
  // プレイヤーごとに違う並びになるよう、番号を大きく散らしてから混ぜる。
  // 乗算と排他的論理和だけなので、実行環境をまたいでも同じ値になる。
  return (matchSeed ^ Math.imul(playerId + 1, 0x9e3779b1)) >>> 0;
}

function countDown(memory: CpuMemory): void {
  memory.thinkIn -= 1;
  if (memory.bombBan > 0) memory.bombBan -= 1;
  if (memory.skillCool > 0) memory.skillCool -= 1;
}

/** 進行中のボタン操作から、この tick のぶんを取り出す。終わったら片付ける。 */
function takeStep(memory: CpuMemory): MacroStep | null {
  const macro = memory.macro;
  if (macro === null) return null;
  const step = macro.next();
  if (!macro.running) memory.macro = null;
  return step;
}

/** ボタンと向きを1つの入力にまとめる。 */
function compose(me: PlayerState, step: MacroStep | null, direction: Direction | null): PlayerInput {
  const pressed = direction === null ? null : compensateReverse(me, direction);
  return {
    up: pressed === 'up',
    down: pressed === 'down',
    left: pressed === 'left',
    right: pressed === 'right',
    bomb: step?.bomb ?? false,
    action: step?.action ?? false,
  };
}
