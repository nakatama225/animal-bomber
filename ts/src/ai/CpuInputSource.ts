import { cellOf, type Direction } from '../domain/core/Coord.js';
import { Rng } from '../domain/core/Rng.js';
import { secondsToTicks, TICKS_PER_SECOND } from '../domain/core/Tick.js';
import type { InputSource } from '../domain/input/InputSource.js';
import { IDLE_INPUT, type PlayerInput } from '../domain/input/PlayerInput.js';
import { playerById } from '../domain/query/BoardQuery.js';
import { DangerMap } from '../domain/query/DangerMap.js';
import type { PlayerId, PlayerState } from '../domain/state/PlayerState.js';
import { isAlive, isFrozen } from '../domain/state/PlayerState.js';
import type { WorldState } from '../domain/state/WorldState.js';
import { decideBomb } from './BombPlacement.js';
import { decide, type CpuBehavior } from './CpuBehavior.js';
import { CpuContext } from './CpuContext.js';
import type { CpuLevel } from './CpuLevel.js';
import { freshMemory, type CpuMemory } from './CpuMemory.js';
import type { CpuButton } from './CpuPlan.js';
import { BLIND_MIN_SECONDS, BLIND_SPREAD_SECONDS, NOTICE_WITHIN, SHARP_THINK_SECONDS } from './margins.js';
import { compensateReverse, directionAlong } from './PathFollower.js';
import { DEFAULT_CHAIN } from './behaviors/DefaultChain.js';
import { NegibonPilot } from './NegibonPilot.js';
import { tacticOf } from './tactics/registry.js';

/** この tick に押すもの。向きは行きたい向き（反転を打ち消す前）。 */
interface Intent {
  readonly direction: Direction | null;
  readonly buttons: readonly CpuButton[];
}

const NOTHING: Intent = Object.freeze({ direction: null, buttons: [] });

/**
 * CPU の操作の出どころ。
 *
 * キーボードやゲームパッドと同じく、1 tick ごとに `PlayerInput` を返すだけ。
 * ゲーム本体からは人間と区別がつかない。
 *
 * ## 1 tick の流れ（原型 cpuUpdate と同じ順）
 *
 * 1. 考え直すまでの間隔・爆弾を控える残り・とくぎの抽選の待ちを1つ減らす
 * 2. 危険の地図を作り、立っているマス（体の中心のマス）が危ないかを見る。弱い CPU は見落とす
 * 3. 泣いている・はまっている間は何もしない。移動を乗っ取る振る舞いの最中は、戦い方が考え続けると
 *    言わない限り何もしない（原型は、穴を掘る・舌を伸ばす間は待ち、体当たりで走る技の最中は考え続ける）
 * 4. 考える前の技（戦い方の `beforePlan`）。使った tick に何もしない技なら、ここで返す
 * 5. 危なくなったのに逃げていない、逃げ先が危なくなった、なら間隔を待たずに考え直す。間隔が来ていれば考え直す
 * 6. 滑っている間は、歩かず、爆弾も置かず、歩いたあとの技も無い（原型は滑って帰る）
 * 7. 経路を1歩。爆弾を置きたい計画なら、逃げ切れるかを確かめて置く。最後に歩いたあとの技（戦い方の `afterMove`）
 *
 * どれも、tick の始めの盤面を見て決める。ゲームの側は、この入力を 動く → 爆弾 → 技 の順で効かせるので、
 * 原型の CPU が1フレームの中で 歩く → 置く → とくぎ と呼んでいたのと同じ順になる。
 *
 * ## ⚠️ 押した瞬間でしか効かない
 *
 * ゲームの側はボタンを「前の tick は押していない」ときだけ押したと読む。前の tick に押したボタンは、
 * この tick には押さない（原型の CPU は続くフレームで関数を呼べたが、そうなる場面はほとんど無い）。
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

    countDown(this.#memory);
    return compose(me, this.#decide(world, me));
  }

  /** 原型 cpuUpdate の本体。この tick に押すものを決める。 */
  #decide(world: Readonly<WorldState>, me: PlayerState): Intent {
    const memory = this.#memory;
    const here = cellOf(me.position);
    const danger = DangerMap.of(world);
    const inDanger = this.#noticeDanger(danger.at(here) < NOTICE_WITHIN);

    // 泣いている・はまっている間は何もしない（原型の CPU も同じ）。
    if (isFrozen(me)) return NOTHING;
    const tactic = tacticOf(me.animal);
    if (me.action?.drivesMovement === true && tactic.thinksDuringAction !== true) return NOTHING;

    const ctx = new CpuContext(world, me, here, danger, inDanger, this.#level, memory, this.#rng);
    const early = tactic.beforePlan;
    const usedEarly = early !== undefined && ctx.canPress(early.button) && early.when(ctx);
    if (usedEarly && early.endsTurn) return { direction: null, buttons: [early.button] };

    this.#replanIfNeeded(ctx);

    // 滑っている間は操作が効かない。原型の CPU は滑らせて、そのフレームを終える。
    const buttons: CpuButton[] = usedEarly ? [early.button] : [];
    if (me.effects.has('slide')) return { direction: null, buttons };

    // 経路を1歩。着いたマスはここで並びから消える。
    const walk = directionAlong(me, memory.path);
    // 考える前の技を使った tick は、歩かず・置かず・歩いたあとの技も使わない（その技が移動を乗っ取り、
    // 置けなくする。原型も、そのフレームは歩けず置けない）。
    if (usedEarly) return { direction: null, buttons };

    const placing = decideBomb(ctx, walk ?? me.facing);
    if (placing !== null) buttons.push(placing);
    if (tactic.afterMove !== undefined && ctx.canPress('special') && tactic.afterMove(ctx)) buttons.push('special');
    return { direction: walk, buttons };
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
   * 間隔が来ていれば、次の計画を決める（原型 cpuUpdate の「考え直し」）。
   *
   * 危なくなったのにまだ逃げていない、または逃げている先が危なくなったなら、間隔を待たずに考え直す。
   */
  #replanIfNeeded(ctx: CpuContext): void {
    const memory = ctx.memory;
    if (ctx.inDanger && memory.mode !== 'flee') memory.thinkIn = 0;
    const goal = memory.path[memory.path.length - 1];
    if (ctx.inDanger && memory.mode === 'flee' && goal !== undefined && !ctx.danger.isSafe(goal)) {
      memory.thinkIn = 0;
    }
    if (memory.thinkIn > 0) return;

    // 危ないときだけ判断を詰める強さもある。ふだんは表の間隔のまま。
    const seconds = ctx.inDanger && ctx.level.sharp ? SHARP_THINK_SECONDS : ctx.level.thinkSeconds;
    memory.thinkIn = Math.max(1, Math.ceil(seconds * (1 + memory.jitter) * TICKS_PER_SECOND));

    const plan = decide(this.#chain, ctx);
    memory.mode = plan.mode;
    memory.path = [...plan.path];
    memory.wantBomb = plan.wantBomb;
  }
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

/**
 * 押すものを1つの入力にまとめる。
 *
 * 向きは、反転がかかっていれば逆にしておく（`compensateReverse`）。押さないボタンは離す。
 * 前の tick に押したボタンは、決める側（`CpuContext.canPress`）がこの tick に選ばない。
 */
function compose(me: PlayerState, intent: Intent): PlayerInput {
  const pressed = intent.direction === null ? null : compensateReverse(me, intent.direction);
  return {
    up: pressed === 'up',
    down: pressed === 'down',
    left: pressed === 'left',
    right: pressed === 'right',
    bomb: intent.buttons.includes('bomb'),
    action: intent.buttons.includes('action'),
    special: intent.buttons.includes('special'),
  };
}
