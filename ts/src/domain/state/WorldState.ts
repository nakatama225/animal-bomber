import type { WorldActor } from '../abilities/WorldActor.js';
import { centerOf } from '../core/Coord.js';
import { IdSource } from '../core/EntityId.js';
import { Rng } from '../core/Rng.js';
import { StateHasher } from '../core/StateHash.js';
import { secondsToTicks, tick, type Tick } from '../core/Tick.js';
import { IDLE_INTENT, packIntent } from '../intent/PlayerIntent.js';
import { ROUND_SECONDS, SPAWN_CELLS, STARTING_HP } from '../rules/tuning.js';
import type { Blast, Bomb } from './Bomb.js';
import { EffectBag } from './EffectBag.js';
import type { Item } from './Item.js';
import type { Board } from './Board.js';
import { buildBoard } from './Board.js';
import { ALIVE, type Life } from './Life.js';
import type { PlayerId, PlayerState } from './PlayerState.js';

/**
 * 試合のいまの状態すべて。
 *
 * **この構造体に入っているものだけが、試合の結果を左右する。** 画面の
 * 見た目・音・粒子はここに含まれない。だから「同じ状態から同じ意思を
 * 与えれば同じ結果になる」が成り立つ。
 *
 * 逆に言えば、ここに何かを足すときは「それが結果を左右するか」を
 * 判断することになる。左右しないものを足すと、通信対戦で
 * 突き合わせる対象が無駄に増える。
 */
export interface WorldState {
  /** いままでに進めた tick 数。 */
  now: Tick;
  /**
   * 時間切れになる tick。
   *
   * 試合の設定の制限時間から始まり、サドンデスに入るとその時点から延長戦の長さぶん先に
   * 置き直す。全員が同じ tick に倒れて延長戦に入った場合は、早まることもある。
   * ⚠️ 残り時間の判定は、設定ではなくこちらを見る。設定の値は延長を知らない。
   */
  endsAt: Tick;
  /**
   * このラウンドがサドンデスに入ったか。
   *
   * 盤面はラウンドごとに作り直すので、「このラウンドで延長を使ったか」と
   * 同じ意味になる。延長は1ラウンドに1回だけ。
   */
  suddenDeath: boolean;
  readonly board: Board;
  readonly players: PlayerState[];
  /** 盤面に置かれている爆弾。置かれた順に並ぶ。 */
  bombs: Bomb[];
  /** いま出ている爆風。 */
  blasts: Blast[];
  /** 盤面に落ちているアイテム。 */
  items: Item[];
  /** 自分で動き続けるもの（飛び道具・落とし穴など）。 */
  actors: WorldActor[];
  /** 結果に影響する乱数。見た目の乱数はここに入れない。 */
  readonly rng: Rng;
  /** 盤面に置かれるものの識別子を発番する。 */
  readonly ids: IdSource;
}

/** 試合を始めるときの設定。 */
export interface WorldSeed {
  /** 盤面とアイテム抽選に使う種。同じ種なら同じ試合になる。 */
  readonly seed: number;
  /** 参加する動物。プレイヤー番号の順に並べる。 */
  readonly animals: readonly string[];
  /** 1ラウンドの制限時間。省略した場合は既定の長さ。 */
  readonly roundLimit?: Tick;
  /**
   * プレイヤーごとの初期体力（半分の単位）。動物ごとの上乗せを足す前の値。
   * 省略した場合は全員が既定の値で始まる。
   */
  readonly startingHp?: readonly number[];
  /**
   * 動物ごとの初期値の上乗せ。
   *
   * ⚠️ ここで能力の表を引かず、呼び出し側から受け取る。引いてしまうと
   * 「状態」が「動物の振る舞い」を知ることになり、依存が逆流する。
   * 省略した場合は全員が素の値で始まる。
   */
  readonly bonusOf?: (animal: string) => StartingBonus;
}

/** 動物ごとの、始まりの上乗せ。 */
export interface StartingBonus {
  /** 体力（半分の単位）。 */
  readonly hp: number;
  readonly power: number;
  readonly bombs: number;
}

const NO_BONUS: StartingBonus = { hp: 0, power: 0, bombs: 0 };

/**
 * 試合の初期状態を作る。
 *
 * ⚠️ 作る順序が結果を決める。盤面を先に作り、そのあとプレイヤーを置く。
 * 逆にすると乱数を引く回数が変わり、同じ種でも別の盤面になる。
 */
export function createWorld(config: WorldSeed): WorldState {
  const startingHp = config.startingHp;
  if (startingHp !== undefined && startingHp.length !== config.animals.length) {
    throw new Error(`初期体力の数（${startingHp.length}）が動物の数（${config.animals.length}）と合わない`);
  }
  const rng = new Rng(config.seed);
  const board = buildBoard(rng, SPAWN_CELLS);

  const players: PlayerState[] = config.animals.map((animal, index) => {
    // プレイヤーは最大4人。開始位置（SPAWN_CELLS）と同じ数に揃えてある。
    const spawn = SPAWN_CELLS[index];
    if (spawn === undefined) {
      throw new Error(`開始位置が足りない: ${index}`);
    }
    const bonus = config.bonusOf?.(animal) ?? NO_BONUS;
    return {
      id: index as PlayerId,
      animal,
      position: centerOf(spawn),
      facing: index < 2 ? 'down' : 'up',
      life: ALIVE,
      hp: (startingHp?.[index] ?? STARTING_HP) + bonus.hp,
      shoes: 0,
      power: 1 + bonus.power,
      maxBombs: 1 + bonus.bombs,
      activeBombs: 0,
      invulnerableUntil: tick(0),
      walked: 0,
      previousIntent: IDLE_INTENT,
      effects: new EffectBag(),
      specialCharges: 0,
      action: null,
      // ⚠️ -1 はロックの印。ラウンド開始時から押しっぱなしのボタンは、
      // 一度離すまで技が出ない。パッドは次の tick で押下が戻るため、
      // これが無いと開始 0.5 秒でとくぎが暴発する。
      actionHeld: tick(-1),
      abilityCooldown: tick(0),
      lastHitBy: null,
    };
  });

  return {
    now: tick(0),
    endsAt: config.roundLimit ?? secondsToTicks(ROUND_SECONDS),
    suddenDeath: false,
    board,
    players,
    bombs: [],
    blasts: [],
    items: [],
    actors: [],
    rng,
    ids: new IdSource(),
  };
}

/**
 * 状態を1つの数値に要約する。
 *
 * 混ぜる順序が結果を決めるので、**ここで決めた順序を変えない**。
 * 変えると、ずれていないのにずれたと判定される。
 *
 * 乱数を引いた回数も混ぜている。状態だけを比べると「どこかがずれた」
 * までしか分からないが、引いた回数のずれが分かると
 * 「ゲームの乱数を余計に引いた／引かなかった」に絞り込める。
 */
export function hashWorld(world: WorldState): number {
  const hasher = new StateHasher();
  hasher.int(world.now);
  hasher.int(world.endsAt);
  hasher.bool(world.suddenDeath);
  hasher.text(world.board.encode());
  hasher.int(world.rng.calls);
  hasher.int(world.ids.issued);

  for (const player of world.players) {
    hasher
      .int(player.id)
      .text(player.animal)
      .float(player.position.x)
      .float(player.position.y)
      .text(player.facing);
    hashLife(hasher, player.life);
    hasher
      .int(player.hp)
      .int(player.shoes)
      .int(player.power)
      .int(player.maxBombs)
      .int(player.activeBombs)
      .int(player.invulnerableUntil)
      .int(packIntent(player.previousIntent))
      .text(player.effects.encode())
      .int(player.specialCharges)
      .text(player.action?.kind ?? '')
      .int(player.actionHeld)
      .int(player.abilityCooldown)
      .int(player.lastHitBy ?? -1);
  }

  // 配列の並び順も結果の一部として混ぜる。並びが違えば誘爆の順序が変わる。
  for (const bomb of world.bombs) {
    hasher
      .int(bomb.id)
      .int(bomb.cell.col)
      .int(bomb.cell.row)
      .int(bomb.owner)
      .int(bomb.power)
      .int(bomb.fuse)
      .bool(bomb.chained)
      .int(bomb.passThrough.size);
  }
  for (const blast of world.blasts) {
    hasher
      .int(blast.id)
      .int(blast.cell.col)
      .int(blast.cell.row)
      .int(blast.owner)
      .bool(blast.isCenter)
      .int(blast.remaining);
  }
  for (const item of world.items) {
    hasher.int(item.id).int(item.cell.col).int(item.cell.row).text(item.kind);
  }
  for (const actor of world.actors) {
    hasher.text(actor.kind).text(actor.encode());
  }

  return hasher.value;
}

/**
 * プレイヤーの状態（盤面・外周・退場）を混ぜる。外周にいる間だけ持つ値は、そのときだけ混ぜる。
 *
 * ⚠️ 状態を1つ足したら、ここにも足す。書き忘れると、その状態の値がずれても
 * 検出できない。`never` への代入は、書き忘れをコンパイルエラーにするためのもの。
 */
function hashLife(hasher: StateHasher, life: Life): void {
  hasher.text(life.kind);
  switch (life.kind) {
    case 'alive':
    case 'out':
      return;
    case 'negibon':
      hasher.float(life.along).int(life.readyAt);
      return;
    default: {
      const unhandled: never = life;
      throw new Error(`扱っていない状態: ${JSON.stringify(unhandled)}`);
    }
  }
}
