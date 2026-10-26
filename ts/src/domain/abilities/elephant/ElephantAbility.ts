import { cellOf, sameCell, step, type Cell } from '../../core/Coord.js';
import { secondsToTicks, tick } from '../../core/Tick.js';
import type { SimEvent } from '../../events/SimEvent.js';
import { removeBomb } from '../../mutations/bombs.js';
import { bombAt } from '../../query/BoardQuery.js';
import type { Ability } from '../Ability.js';
import { NEUTRAL_ABILITY } from '../Ability.js';
import { ChargeAction } from './ChargeAction.js';

/** 鼻水が届くマス数（原型の SNOT_RANGE）。 */
const SNOT_RANGE = 2;

/** 鼻水を吹いたあとの間隔（原型の SNOT_COOL 5 秒）。 */
const SNOT_COOLDOWN = secondsToTicks(5);

/** 流されたうんこが溶けきるまで（原型の SNOT_MELT 0.45 秒。吹いた tick から数えて 27 tick 目に消える）。 */
const MELT_TICKS = tick(27);

/**
 * ぞう。
 *
 * 遅いかわりに火力と体力が高い。通常技は鼻水噴射、とくぎは突進。
 *
 * 長押しの時間を 1.5 秒と長めに取ってあるのは、突進が強い技だから。
 * 強い技ほど、出すまでの隙を大きくする。
 */
export const ELEPHANT: Ability = {
  ...NEUTRAL_ABILITY,
  key: 'elephant',
  speedMultiplier: 0.92,
  powerBonus: 2,
  /** 体力は半分の単位で持つので、1個ぶんは 2。 */
  hpBonus: 2,
  holdTicks: secondsToTicks(1.5),

  /**
   * 鼻水噴射（原型の elephantSnot）。正面2マスの、爆弾の火を消し（爆弾ごと消え、置いたプレイヤーの手持ちは戻る）、
   * うんこを流す（0.45 秒かけて溶けて消え、溶けている間は踏んでも効果が無い）。5 秒に1回。
   *
   * 柱の向こうへは届かない。壊せるブロックのマスまでは届き、その先へは届かない。
   * 爆風は消せない。爆発している最中の爆弾も消せない。とくぎで撒かれたうんこは流せない。
   * 何も消せなくても、吹けば間隔は始まる（原型も同じ）。
   */
  onTap(world, player) {
    if (player.abilityCooldown > 0) return { action: null, events: [] };
    player.abilityCooldown = tick(SNOT_COOLDOWN);
    const events: SimEvent[] = [];
    const sprayedCells: Cell[] = [];
    const here = cellOf(player.position);
    for (let distance = 1; distance <= SNOT_RANGE; distance += 1) {
      const cell = step(here, player.facing, distance);
      const tile = world.board.at(cell);
      if (tile === 'hard') break;
      sprayedCells.push(cell);
      const bomb = bombAt(world, cell);
      if (bomb !== undefined && !bomb.chained) {
        removeBomb(world, bomb);
        events.push({ type: 'bombDoused', cell, owner: bomb.owner });
      }
      const index = world.items.findIndex((item) => sameCell(item.cell, cell));
      const item = index >= 0 ? world.items[index] : undefined;
      // 流し直すと、溶けきるまでの長さを数え直す（原型も溶けかけのうんこに吹き直すと数え直す）。
      if (item !== undefined && item.kind === 'poop' && item.scatteredBy === undefined) {
        world.items[index] = { ...item, meltingUntil: tick(world.now + MELT_TICKS) };
      }
      if (tile === 'soft') break;
    }
    // 水しぶきは届いたマスごとに出す（原型も、柱のマスとその先には出さない）。
    events.push({ type: 'sprayed', player: player.id, cells: sprayedCells, facing: player.facing });
    return { action: null, events };
  },

  onHold(_world, player) {
    return { action: new ChargeAction(player.facing), events: [] };
  },
};
