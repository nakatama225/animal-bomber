import { sameCell, step, type Cell, type Direction } from '../../core/Coord.js';
import { tick, type Tick } from '../../core/Tick.js';
import type { SimEvent } from '../../events/SimEvent.js';
import { applyItem } from '../../mutations/items.js';
import { bombAt, playersOn } from '../../query/BoardQuery.js';
import type { ItemKind } from '../../rules/items.js';
import type { PlayerId, PlayerState } from '../../state/PlayerState.js';
import type { WorldState } from '../../state/WorldState.js';
import type { ActiveAction } from '../ActiveAction.js';
import type { WorldActor } from '../WorldActor.js';

/** 舌が届くいちばん長いマス数（原型の TONGUE_MAX）。焼けると、そのラウンドはこれより短くなる。 */
export const TONGUE_REACH = 10;

/** 舌が焼き切れたときに泣く長さ（原型の TONGUE_BURN_STUN 3 秒）。 */
const BURN_STUN: Tick = tick(180);

/** 焼けた舌が1マス戻るまでの長さ（原型の TONGUE_REGEN 10 秒）。 */
const REGEN_TIME: Tick = tick(600);

/**
 * 伸ばし始めてから elapsed tick までに、舌が何マスぶん動いたか（伸びるのと戻るのを合わせて数える）。
 *
 * 原型は 1マス 0.125 秒（TONGUE_STEP）で、1/60 秒ずつ足していくと k マス目は floor(7.5k)+1 回目に動く
 * （7 と 8 フレームが交互に来る）。それを tick の整数だけで書くと floor((2·elapsed − 1) / 15) になる。
 */
function stepsBy(elapsed: Tick): number {
  return Math.max(0, Math.floor((2 * elapsed - 1) / 15));
}

/**
 * 焼けた舌。そのラウンドは焼けたマスの手前までしか伸びず、10 秒ごとに1マス戻る（原型の tongueLimit・tongueRegen）。
 *
 * 盤面の側の物として持つのは、ラウンドが始まり直すとき（延長戦も含む）に盤面の物と一緒に片付き、
 * 長さが元に戻るから（原型もラウンドの始まりと延長戦で戻す）。プレイヤーの状態に、1つの動物のための
 * 項目を足さずに済む。元の長さまで戻ったら消える。
 */
export class BurntTongueActor implements WorldActor {
  readonly kind = 'burntTongue';
  /** 持ち主の番に、状態の時間を減らす前に戻す（原型はプレイヤーごとの効果の処理の中で戻す）。 */
  readonly turn = 'owner';
  #limit: number;
  #untilRegen: Tick = REGEN_TIME;

  constructor(
    readonly owner: PlayerId,
    limit: number,
  ) {
    this.#limit = limit;
  }

  /** いま伸ばせるマス数。 */
  get limit(): number {
    return this.#limit;
  }

  /** 次に1マス戻るまでの残り。状態の表示のためだけに読む。 */
  get untilRegen(): Tick {
    return this.#untilRegen;
  }

  /** もう一度焼けた。短いほうを採り、戻るまでの時間を数え直す。 */
  burnTo(limit: number): void {
    this.#limit = Math.min(this.#limit, limit);
    this.#untilRegen = REGEN_TIME;
  }

  /** 1 tick 進める。1マス戻ったら知らせる（画面の通知のため。原型 L4307 は、元の長さまで戻った回にも出す）。 */
  tick(): { events: SimEvent[]; done: boolean } {
    this.#untilRegen = tick(this.#untilRegen - 1);
    const events: SimEvent[] = [];
    if (this.#untilRegen <= 0) {
      this.#limit = Math.min(TONGUE_REACH, this.#limit + 1);
      this.#untilRegen = REGEN_TIME;
      events.push({ type: 'reachRestored', player: this.owner, reach: this.#limit });
    }
    return { events, done: this.#limit >= TONGUE_REACH };
  }

  encode(): string {
    return `${this.owner},${this.#limit},${this.#untilRegen}`;
  }
}

/** そのプレイヤーの焼けた舌。焼けていない（伸ばせる長さが元のまま）なら undefined。 */
export function burntTongueOf(world: Readonly<WorldState>, owner: PlayerId): BurntTongueActor | undefined {
  return world.actors.find(
    (actor): actor is BurntTongueActor => actor instanceof BurntTongueActor && actor.owner === owner,
  );
}

/** そのプレイヤーがいま伸ばせる舌のマス数。焼けていなければ TONGUE_REACH。CPU が「届くか」を判断するのにも使う。 */
export function tongueReachOf(world: Readonly<WorldState>, player: PlayerState): number {
  return burntTongueOf(world, player.id)?.limit ?? TONGUE_REACH;
}

/**
 * かえるの通常技。舌を伸ばして、遠くのアイテムを引き寄せる。
 *
 * ⚠️ 良いものも悪いものも区別なく掴む。かえるは効果が2倍になるので、
 * 何を掴むか分からないまま伸ばすのは博打になる。
 * 選べるようにすると、2倍という長所だけが残って短所が消える。
 *
 * 伸ばしている間は動けない。何かに当たるか伸びきったら、同じ速さで引っ込める。往復し終わるまで隙ができる。
 * 伸びきったかは1マス伸びるたびにその時の長さで見る（伸ばしている間に焼けた舌が1マス戻れば、そのぶん伸びる）。
 * 掴んだアイテムは、舌が戻りきったときに適用される（原型の updateTongue）。掴んだ瞬間は掴んだ音だけ、拾った音は適用されたとき。
 *
 * 伸びている舌の上に爆風が来ると焼き切れる（原型の tongueBurnCheck）：掴んでいたものは焦げて消え、
 * 3 秒泣き、そのラウンドは焼けたマスの手前までしか伸びなくなる（`BurntTongueActor`）。
 */
export class TongueAction implements ActiveAction {
  readonly kind = 'tongue';
  readonly drivesMovement = true;
  readonly damageCap = null;
  readonly untouchable = false;
  readonly canPlaceBomb = false;
  /** 往復し終わるまで、技のボタンは無効（原型の doAction・doSpecial）。 */
  readonly blocksButtons = true;
  readonly sweepsItems = false;
  /**
   * 倒れても舌は外さずに止めておき、焼けたかは見続ける（原型と同じ）。原型の toNegibon（L2255）は tongue を消さず
   * （退場 L1700 でも残る）、舌を進めるのは盤面にいるときだけ（L4320-4322）、焼けたかの確認（L4395）は状態を
   * 問わない。外周にいる間に止まった舌の上へ爆風が来ると焼けて、そのラウンドの舌が短くなり、泣く。葱で盤面へ
   * 戻るときに舌も泣く状態も消える（negiHit L2347-2348）が、短くなった長さは残る。
   */
  readonly staysOffBoard = true;

  /** 伸ばし始めたマス。押されて動いても、舌の根元はここのまま（原型も伸ばし始めのマスを覚える）。 */
  readonly #origin: Cell;
  readonly #direction: Direction;
  #elapsed: Tick = tick(0);
  #steps = 0;
  #length = 0;
  #returning = false;
  #caught: ItemKind | null = null;

  constructor(origin: Cell, direction: Direction) {
    this.#origin = origin;
    this.#direction = direction;
  }

  /**
   * 舌がいま伸びている長さ（マス、小数）。描画のためだけに読む。
   *
   * 次に動くまでの途中を、伸びている間は足し、戻っている間は引く。読むだけで、状態も要約（ハッシュ）も変えない。
   */
  get extent(): number {
    const between = (2 * this.#elapsed - 1) / 15 - this.#steps;
    const part = Math.max(0, Math.min(1, between));
    return Math.max(0, this.#length + (this.#returning ? -part : part));
  }

  tick(world: WorldState, player: PlayerState): { events: SimEvent[]; done: boolean } {
    this.#elapsed = tick(this.#elapsed + 1);
    const events: SimEvent[] = [];
    while (this.#steps < stepsBy(this.#elapsed)) {
      this.#steps += 1;
      if (!this.#returning) {
        events.push(...this.#extend(world, player));
        continue;
      }
      this.#length -= 1;
      if (this.#length <= 0) {
        // 戻りきった。掴んでいたものがあれば、ここで適用される（拾った音もここ。原型も applyItem の中で鳴らす）。
        // 倍率は能力が持つが、ここでは参照しない。かえる自身の技なので 2 を直に書いてよい。共通の処理ではないため。
        if (this.#caught !== null) {
          events.push({ type: 'itemTaken', cell: null, kind: this.#caught, taker: player.id, swept: false });
          events.push(...applyItem(world, player, this.#caught, 2));
        }
        return { events, done: true };
      }
    }
    return { events, done: false };
  }

  /** 1マス伸ばす。舌を止めるもの（マス → 爆弾 → ほかのプレイヤー → アイテム）に当たったら、戻り始める。 */
  #extend(world: WorldState, player: PlayerState): SimEvent[] {
    const cell = step(this.#origin, this.#direction, this.#length + 1);
    // 壁の向こうへは届かない。爆弾と、盤面の上のほかのプレイヤーでも止まる（その向こうのアイテムは取らない）。
    if (
      world.board.at(cell) !== 'empty' ||
      bombAt(world, cell) !== undefined ||
      playersOn(world, cell).some((other) => other.id !== player.id)
    ) {
      this.#returning = true;
      return [];
    }
    this.#length += 1;
    const index = world.items.findIndex((item) => sameCell(item.cell, cell));
    const item = index >= 0 ? world.items[index] : undefined;
    if (item !== undefined) {
      world.items.splice(index, 1);
      this.#caught = item.kind;
      this.#returning = true;
      return [{ type: 'techniqueMoment', player: player.id, moment: 'tongueCaught' }];
    }
    // その時の長さで見る（原型の updateTongue も1マスごとに tongueReach を読む）。
    if (this.#length >= tongueReachOf(world, player)) this.#returning = true;
    return [];
  }

  /**
   * 伸びている舌の上に爆風があれば焼き切れる（原型の tongueBurnCheck）。
   *
   * 1 tick の最後（被弾を見たあと）に見るので、爆風が出た tick のうちに焼き切れる（原型も同じ）。
   */
  afterDamage(world: WorldState, player: PlayerState): { events: SimEvent[]; done: boolean } {
    const burnt = this.#burntAt(world);
    if (burnt === null) return { events: [], done: false };
    return { events: this.#burn(world, player, burnt), done: true };
  }

  /** 伸びている舌の上の、いちばん手前の爆風のマス数（1 が根元の隣）。無ければ null。 */
  #burntAt(world: WorldState): number | null {
    for (let i = 1; i <= this.#length; i += 1) {
      const cell = step(this.#origin, this.#direction, i);
      if (world.blasts.some((blast) => sameCell(blast.cell, cell))) return i;
    }
    return null;
  }

  /** 焼き切れた。掴んでいたものは焦げて消え、泣き、そのラウンドは手前までしか伸びなくなる。 */
  #burn(world: WorldState, player: PlayerState, at: number): SimEvent[] {
    const limit = Math.min(tongueReachOf(world, player), at - 1);
    const scar = world.actors.find(
      (actor): actor is BurntTongueActor => actor instanceof BurntTongueActor && actor.owner === player.id,
    );
    if (scar !== undefined) scar.burnTo(limit);
    else world.actors.push(new BurntTongueActor(player.id, limit));
    // 泣く長さは「足す」ではなく「少なくとも 3 秒」（原型は残りと 3 秒の長いほう）。
    const left = player.effects.remaining('stun');
    if (left < BURN_STUN) player.effects.add('stun', tick(BURN_STUN - left), BURN_STUN);
    // 焼けたマスに煙を出す（原型の puff）。
    const cell = step(this.#origin, this.#direction, at);
    return [
      { type: 'burntOff', player: player.id, cell },
      { type: 'effectApplied', target: player.id, effect: 'stun', pushedBy: null },
    ];
  }
}
