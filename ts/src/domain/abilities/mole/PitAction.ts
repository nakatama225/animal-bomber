import { cellOf, sameCell, type Cell } from '../../core/Coord.js';
import { tick, type Tick } from '../../core/Tick.js';
import type { SimEvent } from '../../events/SimEvent.js';
import type { PlayerId } from '../../state/PlayerState.js';
import type { PlayerState } from '../../state/PlayerState.js';
import { isAlive } from '../../state/PlayerState.js';
import type { WorldState } from '../../state/WorldState.js';
import type { ActiveAction } from '../ActiveAction.js';
import type { WorldActor } from '../WorldActor.js';

/** 掘り終わるまでの長さ。 */
const DIG_TIME: Tick = tick(90);

/** 落ちた相手が動けない長さ。 */
const HOLD_TIME: Tick = tick(180);

/** 穴が残る長さ。 */
const PIT_LIFETIME: Tick = tick(3600);

/**
 * 掘られた落とし穴。
 *
 * ⚠️ 盤面には見えない。踏むまで存在が分からないのがこの技の要点で、
 * 見えていると誰も踏まない。
 *
 * 掘った本人には発動しない。自分の穴で自分が止まると、掘る判断が
 * そもそも成り立たなくなる。
 */
export class PitActor implements WorldActor {
  readonly kind = 'pit';
  #remaining: Tick = PIT_LIFETIME;

  constructor(
    readonly cell: Cell,
    readonly owner: PlayerId,
  ) {}

  tick(world: WorldState): { events: SimEvent[]; done: boolean } {
    this.#remaining = tick(this.#remaining - 1);

    for (const player of world.players) {
      if (player.id === this.owner || !isAlive(player)) continue;
      if (!sameCell(cellOf(player.position), this.cell)) continue;
      player.effects.add('stun', HOLD_TIME, tick(HOLD_TIME * 2));
      // 乗っ取り中の振る舞いも打ち切る。穴は無敵でも避けられない。
      player.action = null;
      return {
        events: [{ type: 'effectApplied', target: player.id, effect: 'stun' }],
        done: true,
      };
    }
    return { events: [], done: this.#remaining <= 0 };
  }

  encode(): string {
    return `${this.cell.col},${this.cell.row},${this.owner},${this.#remaining}`;
  }
}

/**
 * もぐらのとくぎ。足元に見えない穴を掘る。
 *
 * 掘っている間は動けない。仕掛ける側にも隙を持たせないと、
 * 逃げながら通り道に穴を並べられてしまう。
 */
export class PitAction implements ActiveAction {
  readonly kind = 'dig';
  readonly drivesMovement = true;
  readonly damageCap = null;
  readonly untouchable = false;
  readonly canPlaceBomb = false;

  #remaining: Tick = DIG_TIME;

  /** 掘り進んだ割合（0〜1）。描画のためだけに読む。状態も要約（ハッシュ）も変えない。 */
  get progress(): number {
    return Math.min(1, Math.max(0, 1 - this.#remaining / DIG_TIME));
  }

  tick(_world: WorldState, _player: PlayerState): { events: SimEvent[]; done: boolean } {
    this.#remaining = tick(this.#remaining - 1);
    return { events: [], done: this.#remaining <= 0 };
  }

  /** 掘り終わった（または打ち切られた）時点で穴が生まれる。 */
  finish(world: WorldState, player: PlayerState): SimEvent[] {
    if (this.#remaining > 0) return []; // 途中で止められたら穴はできない
    world.actors.push(new PitActor(cellOf(player.position), player.id));
    return [];
  }
}
