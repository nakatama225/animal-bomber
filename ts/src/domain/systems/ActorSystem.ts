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
 * 同じ `turn` のものを全員進めてから、`settle` を持つものの `settle` を出た順に呼び、次の `turn` へ移る。
 * 進める順を変えても、盤面の物の並び（`world.actors`。状態の要約に混ぜる順）は出た順のまま。
 */
export class ActorSystem {
  /** 持ち主の番に進めるもの（`turn` が `'owner'`）のうち、そのプレイヤーのものを進める。 */
  stepOwnedBy(world: WorldState, player: PlayerState): SimEvent[] {
    return this.#advance(world, (actor) => actor.turn === 'owner' && actor.owner === player.id);
  }

  /**
   * プレイヤーが動き終わったあとに進めるもの（`turn` が数）を、数の小さい順に進める。
   * 同じ数どうしは出た順。`newestFirst` のものは新しく出たものから（`WorldActor.newestFirst`）。
   * 同じ数のものを全員進めたら、`settle` を出た順に呼んでから次の数へ移る（`WorldActor.settle`）。
   */
  step(world: WorldState): SimEvent[] {
    return this.#advance(world, (actor) => actor.turn !== 'owner');
  }

  #advance(world: WorldState, picks: (actor: WorldActor) => boolean): SimEvent[] {
    const events: SimEvent[] = [];
    // 走査中に増えることがある（爆発して別のものを出すなど）ので、
    // この tick の分だけを先に確定させる。この tick で新しく増えたものは、次の tick から進める。
    const current = [...world.actors];
    const age = (actor: WorldActor): number => current.indexOf(actor);
    const due = current.filter(picks).sort((a, b) => {
      const byTurn = turnOrder(a) - turnOrder(b);
      if (byTurn !== 0) return byTurn;
      const byAge = age(a) - age(b);
      return a.newestFirst === true && b.newestFirst === true ? -byAge : byAge;
    });
    const finished = new Set<WorldActor>();
    for (const group of sameTurnGroups(due)) {
      for (const actor of group) {
        const result = actor.tick(world);
        events.push(...result.events);
        if (result.done) finished.add(actor);
      }
      // 同じ turn の全員が進んでから、役目を終えなかったものの settle を出た順に呼ぶ。
      for (const actor of [...group].sort((a, b) => age(a) - age(b))) {
        if (actor.settle !== undefined && !finished.has(actor)) events.push(...actor.settle(world));
      }
    }
    const added = world.actors.filter((actor) => !current.includes(actor));
    world.actors = [...current.filter((actor) => !finished.has(actor)), ...added];
    return events;
  }
}

/** 並べ替えの鍵。持ち主の番に進めるものは、1人ぶんしか選ばないので順は結果に影響しない。 */
function turnOrder(actor: WorldActor): number {
  return actor.turn === 'owner' ? 0 : actor.turn;
}

/** `turn` の順に並べた列を、同じ `turn` のものごとに区切る。区切った中の並びは保つ。 */
function sameTurnGroups(sorted: readonly WorldActor[]): WorldActor[][] {
  const groups = new Map<WorldActor['turn'], WorldActor[]>();
  for (const actor of sorted) {
    const group = groups.get(actor.turn);
    if (group === undefined) groups.set(actor.turn, [actor]);
    else group.push(actor);
  }
  return [...groups.values()];
}
