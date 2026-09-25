import { cellOf, sameCell, type Direction } from '../../core/Coord.js';
import { tick, type Tick } from '../../core/Tick.js';
import type { SimEvent } from '../../events/SimEvent.js';
import { bombAt } from '../../query/BoardQuery.js';
import { itemDefinition, type ItemKind } from '../../rules/items.js';
import { MAX_SPEED } from '../../rules/tuning.js';
import type { PlayerState } from '../../state/PlayerState.js';
import { isAlive } from '../../state/PlayerState.js';
import type { WorldState } from '../../state/WorldState.js';
import { hurt } from '../../mutations/damage.js';
import { detonate } from '../../mutations/explode.js';
import { applyItem } from '../../mutations/items.js';
import type { ActiveAction } from '../ActiveAction.js';

/** 突進が続く長さ。 */
const CHARGE_DURATION: Tick = tick(300);

/** 突進中の速度（上限速度に対する倍率）。 */
const CHARGE_SPEED_RATIO = 1.25;

/**
 * 突進中に受けるダメージの上限（半分の単位）。
 *
 * ⚠️ 0 にしない。「止まらないが痛い」が突進の設計で、無敵にすると
 * 突進を撃ち続けるだけで勝ててしまう。
 */
const CHARGE_DAMAGE_CAP = 1;

/** ぶつかった相手を押しのける距離（マス）。 */
const KNOCKBACK = 1.1;

/** ぶつかったと判定する距離（マス）。 */
const CONTACT_RANGE = 0.7;

/** 抱えて運べる悪いアイテムの数。 */
const CARRY_LIMIT = 6;

/**
 * ぞうの突進。
 *
 * 柱に当たるまで直進し、途中の壊せるブロックを踏み潰す。爆弾に
 * 突っ込めばその場で起爆させ、自分は止まらない。
 *
 * ## 通り道のアイテムの扱い
 *
 * 良いものはその場で吸い込み、**悪いものは体の前に抱えて運ぶ**。
 * 止まった所の左右へばら撒くか、ぶつかった相手に全部押しつける。
 *
 * 抱える形にしているのは、たまねぎ（泣いて動けない）を踏んで
 * 突進が止まる、という事故を防ぐため。とくぎが通り道のアイテム1つで
 * 中断されると、使う判断そのものが成り立たなくなる。
 *
 * ## この振る舞いが特別扱いを必要としないこと
 *
 * 突進は移動・破壊・取得・被弾の4つに同時に割り込むが、
 * `src/domain/systems/` には「突進」という言葉が1つも無い。
 * System が見るのは `drivesMovement` `damageCap` `untouchable`
 * `canPlaceBomb` の4つの性質だけで、何の振る舞いかは知らない。
 */
export class ChargeAction implements ActiveAction {
  readonly kind = 'charge';
  readonly drivesMovement = true;
  readonly damageCap = CHARGE_DAMAGE_CAP;
  /** 体当たりは当たらないが、爆風は通る。 */
  readonly untouchable = true;
  readonly canPlaceBomb = false;

  #remaining: Tick = CHARGE_DURATION;
  readonly #direction: Direction;
  readonly #carried: ItemKind[] = [];

  constructor(direction: Direction) {
    this.#direction = direction;
  }

  tick(world: WorldState, player: PlayerState): { events: SimEvent[]; done: boolean } {
    const events: SimEvent[] = [];
    this.#remaining = tick(this.#remaining - 1);

    const speed = MAX_SPEED * CHARGE_SPEED_RATIO;
    const delta = STEP_OF[this.#direction];

    // 進む先のマスを見る。半径ぶん先を見ておかないと、めり込んでから止まる。
    const ahead = cellOf({
      x: player.position.x + delta.dx * (0.36 + speed + 0.05),
      y: player.position.y + delta.dy * (0.36 + speed + 0.05),
    });

    // 爆弾に突っ込んだらその場で起爆させる。自分は止まらない。
    const bomb = bombAt(world, ahead);
    if (bomb !== undefined && !bomb.chained) {
      const result = detonate(world, bomb);
      events.push({ type: 'exploded', cell: bomb.cell, owner: bomb.owner, chained: result.chained });
      events.push(...result.events);
    }

    const tile = world.board.at(ahead);
    if (tile === 'hard') {
      // 柱に当たったら終わり。
      return { events, done: true };
    }
    if (tile === 'soft') {
      world.board.set(ahead, 'empty');
      events.push({ type: 'blockDestroyed', cell: ahead });
    }

    player.position = {
      x: player.position.x + delta.dx * speed,
      y: player.position.y + delta.dy * speed,
    };

    // 通路の中心へ寄せる。軸がずれたまま進むと柱に埋まる。
    player.position = this.#alignToLane(player, speed);
    player.walked += speed;

    events.push(...this.#sweepItems(world, player));
    events.push(...this.#pushPlayers(world, player, delta));

    return { events, done: this.#remaining <= 0 };
  }

  /** 止まるときに、抱えていた悪いアイテムを左右へばら撒く。 */
  finish(world: WorldState, player: PlayerState): SimEvent[] {
    if (this.#carried.length === 0) return [];
    const events: SimEvent[] = [];
    const origin = cellOf(player.position);
    const horizontal = this.#direction === 'left' || this.#direction === 'right';
    // 進行方向と直角の両側へ、左右交互に離れながら空きを探す。
    const sides = horizontal
      ? [
          { col: 0, row: -1 },
          { col: 0, row: 1 },
        ]
      : [
          { col: -1, row: 0 },
          { col: 1, row: 0 },
        ];

    let index = 0;
    for (const kind of this.#carried) {
      const order = index % 2 === 0 ? sides : [...sides].reverse();
      let placed = false;
      for (let distance = 1; distance <= 4 && !placed; distance += 1) {
        for (const side of order) {
          const cell = {
            col: origin.col + side.col * distance,
            row: origin.row + side.row * distance,
          };
          if (world.board.at(cell) !== 'empty') continue;
          if (bombAt(world, cell) !== undefined) continue;
          if (world.items.some((item) => sameCell(item.cell, cell))) continue;
          world.items.push({ id: world.ids.take(), cell, kind });
          events.push({ type: 'itemDropped', cell, kind });
          placed = true;
          break;
        }
      }
      index += 1;
    }
    this.#carried.length = 0;
    return events;
  }

  /** 通り道のアイテムを、良いものは吸い込み、悪いものは抱える。 */
  #sweepItems(world: WorldState, player: PlayerState): SimEvent[] {
    const cell = cellOf(player.position);
    const index = world.items.findIndex((item) => sameCell(item.cell, cell));
    if (index < 0) return [];
    const item = world.items[index];
    if (item === undefined) return [];
    world.items.splice(index, 1);

    if (itemDefinition(item.kind).harmful) {
      // 抱えられる数を超えたぶんは踏み潰したことにする。
      if (this.#carried.length < CARRY_LIMIT) this.#carried.push(item.kind);
      return [];
    }
    const events: SimEvent[] = [
      { type: 'itemTaken', cell, kind: item.kind, taker: player.id },
    ];
    events.push(...applyItem(world, player, item.kind));
    return events;
  }

  /** ぶつかった相手を押しのけ、抱えていた悪いアイテムを全部ぶつける。 */
  #pushPlayers(
    world: WorldState,
    player: PlayerState,
    delta: { dx: number; dy: number },
  ): SimEvent[] {
    const events: SimEvent[] = [];
    for (const other of world.players) {
      if (other.id === player.id || !isAlive(other)) continue;
      if (Math.abs(other.position.x - player.position.x) > CONTACT_RANGE) continue;
      if (Math.abs(other.position.y - player.position.y) > CONTACT_RANGE) continue;

      other.position = {
        x: other.position.x + delta.dx * KNOCKBACK,
        y: other.position.y + delta.dy * KNOCKBACK,
      };

      if (this.#carried.length > 0) {
        for (const kind of this.#carried) events.push(...applyItem(world, other, kind));
        this.#carried.length = 0;
      }

      // 相手が当たらない状態なら傷つけない。
      if (other.action?.untouchable === true) continue;
      if (world.now < other.invulnerableUntil) continue;
      events.push(...hurt(world, other, player.id, 2));
    }
    return events;
  }

  #alignToLane(player: PlayerState, speed: number): { x: number; y: number } {
    const horizontal = this.#direction === 'left' || this.#direction === 'right';
    if (horizontal) {
      const target = Math.floor(player.position.y) + 0.5;
      const gap = Math.max(-speed, Math.min(speed, target - player.position.y));
      return { x: player.position.x, y: player.position.y + gap };
    }
    const target = Math.floor(player.position.x) + 0.5;
    const gap = Math.max(-speed, Math.min(speed, target - player.position.x));
    return { x: player.position.x + gap, y: player.position.y };
  }
}

/** 各方向へ1歩ぶんの差分。 */
const STEP_OF: Readonly<Record<Direction, { dx: number; dy: number }>> = {
  up: { dx: 0, dy: -1 },
  down: { dx: 0, dy: 1 },
  left: { dx: -1, dy: 0 },
  right: { dx: 1, dy: 0 },
};
