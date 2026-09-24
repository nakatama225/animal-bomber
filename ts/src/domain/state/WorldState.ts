import { centerOf } from '../core/Coord.js';
import { IdSource } from '../core/EntityId.js';
import { Rng } from '../core/Rng.js';
import { StateHasher } from '../core/StateHash.js';
import { tick, type Tick } from '../core/Tick.js';
import { SPAWN_CELLS } from '../rules/tuning.js';
import type { Board } from './Board.js';
import { buildBoard } from './Board.js';
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
  readonly board: Board;
  readonly players: PlayerState[];
  /** 結果に影響する乱数。見た目の乱数はここに入れない。 */
  readonly rng: Rng;
  /** 盤面に置かれるものの識別子を発番する。 */
  readonly ids: IdSource;
}

/** 試合を始めるときの設定。 */
export interface WorldSeed {
  /** 盤面とアイテム抽選に使う種。同じ種なら同じ試合になる。 */
  readonly seed: number;
  /** 参加する動物。席順に並べる。 */
  readonly animals: readonly string[];
}

/**
 * 試合の初期状態を作る。
 *
 * ⚠️ 作る順序が結果を決める。盤面を先に作り、そのあとプレイヤーを置く。
 * 逆にすると乱数を引く回数が変わり、同じ種でも別の盤面になる。
 */
export function createWorld(config: WorldSeed): WorldState {
  const rng = new Rng(config.seed);
  const board = buildBoard(rng, SPAWN_CELLS);

  const players: PlayerState[] = config.animals.map((animal, index) => {
    // 席は最大4つ。SPAWN_CELLS と同じ数に揃えてある。
    const spawn = SPAWN_CELLS[index];
    if (spawn === undefined) {
      throw new Error(`席が足りない: ${index}`);
    }
    return {
      id: index as PlayerId,
      animal,
      position: centerOf(spawn),
      facing: index < 2 ? 'down' : 'up',
      life: 'alive',
      hp: 6,
      shoes: 0,
      power: 1,
      maxBombs: 1,
      activeBombs: 0,
      invulnerableUntil: tick(0),
      walked: 0,
    };
  });

  return { now: tick(0), board, players, rng, ids: new IdSource() };
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
  hasher.text(world.board.encode());
  hasher.int(world.rng.calls);
  hasher.int(world.ids.issued);
  for (const player of world.players) {
    hasher
      .int(player.id)
      .text(player.animal)
      .float(player.position.x)
      .float(player.position.y)
      .text(player.facing)
      .text(player.life)
      .int(player.hp)
      .int(player.shoes)
      .int(player.power)
      .int(player.maxBombs)
      .int(player.activeBombs)
      .int(player.invulnerableUntil);
  }
  return hasher.value;
}
