import type { WorldActor } from '../abilities/WorldActor.js';
import type { SimEvent } from '../events/SimEvent.js';
import type { PlayerState } from '../state/PlayerState.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 盤面に出ている自律物を進める。
 *
 * 何が出ているかは見ない。`tick` を呼んで、終わったものを外すだけ。
 * 新しい飛び道具が増えても、このファイルは変わらない。
 *
 * いつ進めるかは、それぞれが持つ `turn` で決まる（原型の update の並び。`WorldActor` の説明）。
 * 進める順を変えても、盤面の物の並び（`world.actors`。状態の要約に混ぜる順）は出た順のまま。
 */
export class ActorSystem {
  /** 持ち主の番に進めるもの（`turn` が `'owner'`）のうち、そのプレイヤーのものを進める。 */
  stepOwnedBy(world: WorldState, player: PlayerState): SimEvent[] {
    return this.#advance(world, (actor) => actor.turn === 'owner' && actor.owner === player.id);
  }

  /**
   * プレイヤーが動き終わったあとに進めるもの（`turn` が数）を、数の小さい順に進める。
   * 同じ数どうしは出た順。
   */
  step(world: WorldState): SimEvent[] {
    return this.#advance(world, (actor) => actor.turn !== 'owner');
  }

  #advance(world: WorldState, picks: (actor: WorldActor) => boolean): SimEvent[] {
    const events: SimEvent[] = [];
    // 走査中に増えることがある（爆発して別のものを出すなど）ので、
    // この tick の分だけを先に確定させる。この tick で新しく増えたものは、次の tick から進める。
    const current = [...world.actors];
    const due = current.filter(picks).sort((a, b) => turnOrder(a) - turnOrder(b));
    const finished = new Set<WorldActor>();
    for (const actor of due) {
      const result = actor.tick(world);
      events.push(...result.events);
      if (result.done) finished.add(actor);
    }
    const added = world.actors.filter((actor) => !current.includes(actor));
    world.actors = [...current.filter((actor) => !finished.has(actor)), ...added];
    return events;
  }
}

/** 並べ替えの鍵。持ち主の番に進めるものは、1人ぶんしか選ばないので順は効かない。 */
function turnOrder(actor: WorldActor): number {
  return actor.turn === 'owner' ? 0 : actor.turn;
}
