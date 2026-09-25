import { cellOf, sameCell, step, type Direction } from '../../core/Coord.js';
import { tick, type Tick } from '../../core/Tick.js';
import type { SimEvent } from '../../events/SimEvent.js';
import { applyItem } from '../../mutations/items.js';
import type { PlayerState } from '../../state/PlayerState.js';
import type { WorldState } from '../../state/WorldState.js';
import type { ActiveAction } from '../ActiveAction.js';

/** 舌が届くマス数。CPU が「届くか」を判断するのにも使う。 */
export const TONGUE_REACH = 6;

/** 1マス伸びるのにかかる長さ。 */
const STEP_TIME: Tick = tick(4);

/**
 * かえるの通常技。舌を伸ばして、遠くのアイテムを引き寄せる。
 *
 * ⚠️ 良いものも悪いものも区別なく掴む。かえるは効果が2倍になるので、
 * 何を引くか分からないまま伸ばすのは博打になる。
 * 選べるようにすると、2倍という長所だけが残って短所が消える。
 *
 * 伸ばしている間は動けない。往復し終わるまで隙ができる。
 */
export class TongueAction implements ActiveAction {
  readonly kind = 'tongue';
  readonly drivesMovement = true;
  readonly damageCap = null;
  readonly untouchable = false;
  readonly canPlaceBomb = false;

  readonly #direction: Direction;
  #elapsed: Tick = tick(0);
  #reached = 0;
  #caught = false;

  constructor(direction: Direction) {
    this.#direction = direction;
  }

  tick(world: WorldState, player: PlayerState): { events: SimEvent[]; done: boolean } {
    this.#elapsed = tick(this.#elapsed + 1);

    // 伸びきったら戻り始める。ここでは往路だけを数える。
    const want = Math.min(TONGUE_REACH, Math.floor(this.#elapsed / STEP_TIME));
    const events: SimEvent[] = [];

    while (this.#reached < want && !this.#caught) {
      this.#reached += 1;
      const cell = step(cellOf(player.position), this.#direction, this.#reached);
      // 壁の向こうへは届かない。
      if (world.board.at(cell) !== 'empty') {
        this.#caught = true;
        break;
      }
      const index = world.items.findIndex((item) => sameCell(item.cell, cell));
      if (index < 0) continue;

      const item = world.items[index];
      if (item === undefined) continue;
      world.items.splice(index, 1);
      this.#caught = true;
      events.push({ type: 'itemTaken', cell, kind: item.kind, taker: player.id });
      // 倍率は能力が持つが、ここでは引かない。かえる自身の技なので
      // 2 を直に書いてよい。共通の処理ではないため。
      events.push(...applyItem(world, player, item.kind, 2));
    }

    // 往路と復路で同じだけ時間をかける。
    const done = this.#caught || this.#elapsed >= STEP_TIME * TONGUE_REACH * 2;
    return { events, done };
  }
}
