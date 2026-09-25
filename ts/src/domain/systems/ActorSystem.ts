import type { SimEvent } from '../events/SimEvent.js';
import type { WorldState } from '../state/WorldState.js';

/**
 * 盤面に出ている自律物を進める。
 *
 * 何が出ているかは見ない。`tick` を呼んで、終わったものを外すだけ。
 * 新しい飛び道具が増えても、このファイルは変わらない。
 */
export class ActorSystem {
  step(world: WorldState): SimEvent[] {
    const events: SimEvent[] = [];
    const alive = [];
    // 走査中に増えることがある（爆発して別のものを出すなど）ので、
    // この tick の分だけを先に確定させる。
    const current = [...world.actors];
    for (const actor of current) {
      const result = actor.tick(world);
      events.push(...result.events);
      if (!result.done) alive.push(actor);
    }
    // この tick で新しく増えたものは、次の tick から進める。
    const added = world.actors.filter((actor) => !current.includes(actor));
    world.actors = [...alive, ...added];
    return events;
  }
}
